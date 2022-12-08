#!/usr/bin/env python3
# # -*- coding: utf-8 -*-

#####################################################################
#
# Copyright (C) 2020    Jakub Fišer  <jakub DOT fiser AT eryaf DOT com>
#
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU Lesser General Public
# License as published by the Free Software Foundation; either
# version 2.1 of the License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU
# Lesser General Public License for more details.
#
# You should have received a copy of the GNU Lesser General Public
# License along with this library; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301  USA
#
######################################################################

import argparse
import os
import sh
import yaml
import math
import sys
import re
import json
import io
from urllib.parse import urlparse
from functools import lru_cache, cached_property

# Debian 9 Stretch, Ubuntu 18.04 Bionic and (probably) other older distributions
# need in environment LANG=C.UTF-8 (or other similar specification of encoding)
# to properly function


class PathExistsAction(argparse.Action):
    def test_path(self: object, path) -> str:
        if not os.path.isdir(path):
            raise argparse.ArgumentError(self,
                                         "Path {} does not exist.".format(path))
        if not os.access(path, os.W_OK):
            raise argparse.ArgumentError(self,
                                         "Path {} cannot be written to.".format(path))
        return os.path.realpath(os.path.abspath(path.rstrip(os.sep)))

    def __call__(self, parser, namespace, values, option_string=None):
        if type(values) == list:
            folders = map(self.test_path, values)
        else:
            folders = self.test_path(values)

        setattr(namespace, self.dest, folders)


class NormalizePath():
    def __init__(self: object, path):
        self.path = self.path_raw = path
        self.root_path = ""

    def normalize_path(self: object) -> None:
        self.path = os.path.normpath(self.path_raw)

    def verify_path_exists(self: object) -> None:
        if not os.path.exists(self.path):
            error_message = "Path {} is not a file or directory.".format(
                self.path)
            raise ValueError(error_message)

    def getGitRepositoryRoot(self: object) -> None:
        try:
            self.root_path = sh.git("rev-parse",
                                    "--show-toplevel",
                                    _tty_out=False,
                                    _cwd=self.path).strip().rstrip(os.sep)
        except sh.ErrorReturnCode as e:
            error_message = "Path {} is not a git repository. Error {}".format(
                self.path, e)
            raise ValueError(error_message)

    def __call__(self: object) -> str:
        self.verify_path_exists()
        self.getGitRepositoryRoot()
        return self.root_path

class NormalizeSubdir(NormalizePath):
    def __init__(self: object, *paths):
        self.path_raw = os.path.join(*paths)
        self.normalize_path()

    def check_writable(self: object) -> bool:
        return os.access(self.path, os.W_OK)

    def __call__(self: object) -> str:
        self.verify_path_exists()
        return self.path

class DistroSettings(object):
    yaml_file = "debian-distro-settings.yaml"
    # Optional file for providing environment settings outside of CI
    local_env_file = "local-env.yaml"

    def __init__(self: object, path: str, version=None, architecture=None):
        # Set up paths
        if not path:
            path = os.getcwd()
        self.normalized_path = NormalizePath(path)()
        self.github_dir = NormalizeSubdir(self.normalized_path, '.github')()
        self.read_distro_settings()
        self.read_local_env()

        if version and architecture:
            self.set_os_arch_combination(version, architecture)
        else:
            self.os_arch_is_set = False

    def read_distro_settings(self: object):
        self.yaml_path = os.path.join(self.github_dir, self.yaml_file)
        if not os.path.exists(self.yaml_path):
            error_message = "Config file '{}' not found".format(
                self.yaml_path)
            raise ValueError(error_message)
        with open(self.yaml_path, "r") as reader:
            self.distro_settings = yaml.safe_load(reader)

    def read_local_env(self: object):
        self.local_env_path = os.path.join(self.github_dir, self.local_env_file)
        if not os.path.exists(self.local_env_path):
            return
        with open(self.local_env_path, "r") as reader:
            self.local_env_settings = yaml.safe_load(reader)
        for key, value in self.local_env_settings.items():
            # Set environment variables; don't clobber
            if key not in os.environ:
                os.environ[key] = value

    def env(self, var, default=None):
        # Check and return environment variable; raise exception if not found
        value = os.environ.get(var,None)
        if value is not None:
            return value
        if default is None:
            raise RuntimeError("{} unset in environment".format(var))
        return default

    @property
    def package(self):
        return self.distro_settings['package']

    @property
    def label_prefix(self):
        return self.distro_settings.get(
            'label_prefix', 'io.machinekit.{}'.format(self.package))

    @property
    def project_name(self):
        return self.distro_settings['projectName']

    @property
    def docker_context_path(self):
        # Absolute path to docker context (default '$PWD')
        return os.path.join(
            self.normalized_path, self.distro_settings.get('docker_context_path','.'))

    @property
    def docker_build_context_files(self):
        # Files to copy into Docker build context
        return self.distro_settings.get('dockerBuildContextFiles',[])

    @property
    def source_dir(self):
        # Path to package sources; usually the same as self.normalized_path, but
        # can be a subdirectory
        return NormalizeSubdir(
            self.normalized_path, self.distro_settings.get('sourceDir','.'))()

    @property
    def debian_dir(self):
        # Relative path to debian/ directory (default 'debian/')
        return self.distro_settings.get('debian_dir','debian')

    @property
    def script_pre_cmd(self):
        # Command to run to configure debian image before installing build deps
        return self.distro_settings.get('scriptPreCmd',None)

    @property
    def script_post_cmd(self):
        # Command to run to configure debian image after installing build deps
        return self.distro_settings.get('scriptPostCmd',None)

    @property
    def configure_src_cmd(self):
        # Command to run to configure source tree before package build
        return self.distro_settings.get('configureSourceCmd',None)

    @property
    def parent_dir(self):
        return NormalizeSubdir(os.path.join(self.normalized_path, '..'))()

    def assert_parent_dir_writable(self: object):
        parent_dir = NormalizeSubdir(os.path.join(self.normalized_path, '..'))
        if not parent_dir.check_writable():
            raise ValueError(
                "Directory {0} is not writable.".format(parent_directory()))

    def template(self: object, format: str) -> str:
        replacements = dict(
            PACKAGE = self.package,
            VENDOR = self.os_vendor,
            ARCHITECTURE = self.architecture,
            RELEASE = self.os_release,
        )
        result = format
        for key, val in replacements.items():
            result = result.replace("@{}@".format(key), val)
        return result

    @property
    def image_name(self):
        if getattr(self, "image_name_override", None):  # Allow overriding template
            return self.image_name_override
        self.assert_os_arch_is_set()
        image_name_fmt = self.distro_settings.get(
            'imageNameFmt','@PACKAGE@-@VENDOR@-builder')
        image_name = self.template(image_name_fmt)
        return image_name

    @property
    def image_tag(self):
        self.assert_os_arch_is_set()
        image_tag_fmt = self.distro_settings.get(
            'imageTagFmt','@RELEASE@_@ARCHITECTURE@')
        image_tag = self.template(image_tag_fmt)
        return image_tag

    @property
    def docker_registry_namespace(self: object):
        return "{}/{}".format(
            self.env('DOCKER_REGISTRY_USER'), self.env('DOCKER_REGISTRY_REPO'))

    @property
    def image_registry_name_tag(self):
        registry_url = self.env('DOCKER_REGISTRY_URL')
        registry_hostname = urlparse(registry_url).hostname
        return "{}/{}/{}:{}".format(
            registry_hostname, self.docker_registry_namespace,
            self.image_name, self.image_tag)



    def set_os_arch_combination(self: object, version, architecture) -> bool:
        for os_data in self.distro_settings['matrix']:
            if (os_data['codename'].lower().__eq__(str(version).lower()) or
                 str(os_data['release']).__eq__(version)):
                if architecture.lower() in os_data['architectures']:
                    self.base_image = os_data['baseImage'].lower()
                    self.architecture = architecture.lower()
                    self.os_vendor = os_data['vendor'].lower()
                    self.os_release = str(os_data['release'])
                    self.os_codename = os_data['codename'].lower()
                    self.os_arch_is_set = True
                    return True
        return False

    def assert_os_arch_is_set(self: object) -> None:
        if not self.os_arch_is_set:
            error_message = "No OS+arch set"
            raise RuntimeError(error_message)

    def hash_os_distros(self):
        # Create dicts of the `matrix` config with release and codename as keys
        self._os_distro_dict = {d['release']:d for d in self.distro_settings['matrix']}
        self._os_distro_dict.update({d['codename']:d for d in self.distro_settings['matrix']})

        # Create matrix dict
        self.matrix_dict = md = dict()
        for os_distro in self.distro_settings['matrix']:
            for arch in os_distro.pop('architectures'):
                md[arch, os_distro['release']] = os_distro.copy()
        for k, v in md.items():
            # Add architecture, lower-case vendor, artifact name
            v['architecture'] = k[0]
            v['vendorLower'] = v['vendor'].lower()
            v['artifactNameBase'] = "{}-{}-{}-{}".format(
                self.package, v['vendor'].lower(), v['release'], v['architecture'],)

    @property
    def image_hash_label(self):
        return "{}.image_hash".format(self.label_prefix)

class CloudsmithUploader(DistroSettings):
    def __init__(self: object, path, package_directory):
        super(CloudsmithUploader, self).__init__(path)
        self.package_directory = NormalizeSubdir(package_directory)()
        self.hash_os_distros()

    @cached_property
    def repo_slug(self):
        return self.distro_settings.get('cloudsmith_repo_slug', self.package)

    @cached_property
    def namespace(self: object):
        namespace = os.environ.get("CLOUDSMITH_NAMESPACE", None)
        if namespace:
            sys.stderr.write(
                f'Cloudsmith namespace "{namespace}" from environment\n')
            return namespace
        namespace = self.distro_settings.get('cloudsmith_repo_namespace', None)
        if namespace:
            sys.stderr.write(
                f'Cloudsmith namespace "{namespace}" from config\n')
            return namespace
        raise RuntimeError(
            'Cloudsmith namespace not set in "$CLOUDSMITH_NAMESPACE" env '
            'or in "cloudsmith_namespace" config key')

    @cached_property
    def repo(self: object):
        repos_json = sh.cloudsmith.list.repos(
            '--output-format=json', _tty_out=False)
        repos = json.loads(str(repos_json))
        for repo in repos['data']:
            if (repo['namespace'] == self.namespace
                and repo['slug'] == self.repo_slug):
                break
        else:
            raise ValueError(
                f"No Cloudsmith repo found in {self.namespace} "
                f"namespace with {self.repo_slug} slug")
        sys.stderr.write(
            f"Found Cloudsmith repo, namespace {self.namespace}, "
            f"slug {self.repo_slug}\n")
        return repo


    package_regex = re.compile(r'^[^_]+_(.*)_([^.]*)\.d?deb$')
    def walk_package_directory(self: object):
        # Walk package_directory, yielding (subdir, fname) on matches
        for subdir, _, files in os.walk(self.package_directory):
            for fname in files:
                match = self.package_regex.match(fname)
                if match:
                    yield((subdir, fname))

    ordr_regex = re.compile(r'^([^-]+)-([^-]+)-([^-]+)$')
    def ordr(self: object, subdir):
        topdir = subdir.split('/')[-1]
        match = self.ordr_regex.match(topdir)
        codename = match.group(1)
        for os_distro in self.matrix_dict.values():
            if codename == os_distro['codename']:
                release = os_distro['release']
                distro = os_distro['vendor'].lower()
                return f'{self.namespace}/{self.repo_slug}/{distro}/{release}'
        else:
            sys.stderr.write(f"Unknown release/distro for {subdir}\n")
            sys.exit(1)

    def upload_packages(self: object, dry_run=False):
        for dirname, fname in self.walk_package_directory():
            ordr = self.ordr(dirname)
            args = ['--republish', ordr, fname]
            sys.stderr.write(f"in directory {dirname}, will run:\n")
            sys.stderr.write(f"    cloudsmith push deb {' '.join(args)}\n")
            sys.stderr.flush()
            if not dry_run:
                sh.cloudsmith.push.deb(*args,
                                       _out=sys.stdout.buffer,
                                       _err=sys.stderr.buffer,
                                       _cwd=dirname)

    @classmethod
    def cli(cls):
        parser = argparse.ArgumentParser(
            description="Upload packages to Cloudsmith")

        # Optional arguments
        parser.add_argument("-p",
                            "--path",
                            action=PathExistsAction,
                            dest="path",
                            default=os.getcwd(),
                            help="Path to root of git repository")
        parser.add_argument("--package-directory",
                            default=os.getcwd(),
                            help="Directory containing packages")
        parser.add_argument("--dry-run",
                            action="store_true",
                            help="Show what would be done, but do nothing")

        args = parser.parse_args()

        try:
            cloudsmith_uploader = cls(
                args.path, args.package_directory)
            cloudsmith_uploader.upload_packages(dry_run=args.dry_run)
        except ValueError as e:
            sys.stderr.write(str(e) + '\n')
            sys.exit(1)

class Query(DistroSettings):
    _query_keys = set()
    def __init__(self: object, path, version, architecture):
        super(Query, self).__init__(path, version, architecture)
        self.hash_os_distros()

        if 'GITHUB_CONTEXT' in os.environ:
            with io.StringIO(os.environ['GITHUB_CONTEXT']) as f:
                self._github_context = json.load(f)

    class _query_property:
        query_keys = dict()

        def __init__(self, prop_func):
            self.prop_func = prop_func
            self.doc = prop_func.__doc__

        def __set_name__(self, owner, name):
            self.query_keys[self.prop_func.__name__] = self.doc
            setattr(owner, name, property(self.prop_func))

    @_query_property
    def github_main_matrix(self):
        '''Main matrix used in GitHub Actions'''
        return dict(include=list(self.matrix_dict.values()))

    @_query_property
    def github_os_matrix(self):
        '''OS matrix used in GitHub Actions'''
        distros = self.distro_settings['matrix'].copy()
        updates = self.distro_settings.copy()
        updates.pop('matrix')
        updates.pop('allowedCombinations')
        for d in distros:
            d.update(updates)
        return distros

    @_query_property
    def docker_images(self):
        '''List of Docker images'''
        images = list()
        for os_distro in self.matrix_dict.values():
            release = os_distro['release']
            architecture = os_distro['architecture']
            self.set_os_arch_combination(release, architecture)
            images.append(self.image_name)
        return images


    def list_keys(self):
        for k, doc in self._query_property.query_keys.items():
            print("{}:  {}".format(k, doc))

    def run_query(self, query_key, format="auto", pretty=False):
        if not hasattr(self, query_key):
            raise RuntimeError('No such query key "{}"'.format(query_key))
        value = getattr(self, query_key)
        if format == "auto":
            format = "json" if type(value) in (list, dict) else "str"
        if format == "str":
            print(str(value))
        elif format == "json":
            kwargs = dict(indent=2) if pretty else dict()
            print(json.dumps(value, **kwargs))
        elif format == "yaml":
            print(yaml.dump(value, default_flow_style=False))
        else:
            raise RuntimeError("Unknown format '{}'".format(format))

    @classmethod
    def cli(cls):
        parser = argparse.ArgumentParser(
            description="Query distro YAML and Github context")

        # Optional arguments
        parser.add_argument("-p",
                            "--path",
                            action=PathExistsAction,
                            help="Path to root of git repository")
        parser.add_argument("--version",
                            help="OS version number or codename")
        parser.add_argument("--architecture",
                            help="Debian architecture")
        parser.add_argument("--list-keys",
                            action="store_true",
                            help="List all keys")
        parser.add_argument("--format",
                            choices=["str", "json", "yaml"],
                            default="auto",
                            help="Output format (default: 'json' for objects, else 'str')")
        parser.add_argument("--pretty",
                            action="store_true",
                            help="Output in human-readable format")

        # Positional arguments
        parser.add_argument("query_keys",
                            metavar="QUERY_KEYS",
                            nargs=argparse.REMAINDER,
                            help="Key to query")

        args = parser.parse_args()
        query_obj = cls(path=args.path, version=args.version, architecture=args.architecture)
        if args.list_keys:
            query_obj.list_keys()
        elif args.query_keys:
            for query_key in args.query_keys:
                query_obj.run_query(query_key, format=args.format, pretty=args.pretty)
        sys.exit(0)


if __name__ == "__main__":
    executable = os.path.basename(sys.argv[0])
    if executable == "cloudsmithupload.py":
        CloudsmithUploader.cli()
    elif executable == "querybuild.py":
        Query.cli()
    else:
        sys.stderr.write(f"Unknown command {sys.argv[0]}\n")
        sys.exit(1)
