######################################################################
# Base Image
#
# This image contains basic package development tools and
# configuration to sync container and host user ID for building a
# bind-mounted source tree

ARG DEBIAN_DISTRO_BASE
FROM ${DEBIAN_DISTRO_BASE} AS builder_base

SHELL [ "bash", "-c" ]

###########################
# Generic apt configuration

ENV TERM=dumb

# Apt config:  silence warnings and set defaults
ENV DEBIAN_FRONTEND=noninteractive
ENV DEBCONF_NONINTERACTIVE_SEEN=true
ENV LC_ALL=C.UTF-8
ENV LANGUAGE=C.UTF-8
ENV LANG=C.UTF-8

# Turn off recommends on container OS
RUN printf "%s;\n%s;\n"                 \
    'APT::Install-Recommends "0"'       \
    'APT::Install-Suggests "0"'         \
    > /etc/apt/apt.conf.d/01norecommend

# Update system OS
RUN apt-get update &&     \
    apt-get -y upgrade && \
    apt-get clean

####################################
# Set up user environment

ENV USER=builder

RUN addgroup --gid 1000 ${USER} &&                            \
    adduser --uid 1000 --ingroup ${USER} --home /home/${USER} \
    --shell /bin/bash --disabled-password --gecos "" ${USER}

RUN apt-get update &&        \
    apt-get install -y       \
        sudo                 \
    && \
    apt-get clean

COPY .github/entrypoint /usr/bin/entrypoint

RUN echo "${USER} ALL=(ALL:ALL) NOPASSWD: ALL" >> /etc/sudoers

ENTRYPOINT [ "/usr/bin/entrypoint" ]

######################################################################

RUN apt-get update \
    && apt-get install -y \
        build-essential \
        fakeroot \
        devscripts \
        equivs \
        ccache \
        lintian \
        python3-debian \
        python3-setuptools \
        python3-pip \
        git \
        lsb-release \
    # Mint 17 has no systemd package
    && (apt-get install -y systemd | true) \
    && apt-get clean

######################################################################
# Builder Base Cross-builder image
#
# This image adds configuration and tools for cross-building packages
# when host architecture differs from the build architecture

FROM builder_base AS builder_base_arch

ARG ARCHITECTURE
ENV ARCHITECTURE=${ARCHITECTURE}
ENV IN_BUILDER=1

RUN if ! dpkg-architecture -e${ARCHITECTURE}; then \
        dpkg --add-architecture ${ARCHITECTURE}; \
    fi

# Ubuntu ports repos for cross-building
RUN if test $(source /etc/os-release; echo $ID) = ubuntu \
        -a ${ARCHITECTURE} != amd64 \
	    -a ${ARCHITECTURE} != i386; then \
	CODENAME=$(source /etc/os-release; echo $VERSION_CODENAME) && \
	sed </etc/apt/sources.list \
	    >/etc/apt/sources.list.d/ubuntu-ports-${ARCHITECTURE}.list \
	    -e "/http:\/\/security/ d"  -e "/^#/ d"  -e "/^$/ d" \
	    -e "s/^deb /deb [arch=${ARCHITECTURE}] /" \
	    -e "s,http://archive.ubuntu.com/ubuntu/,http://ports.ubuntu.com/ubuntu-ports/," && \
        cat /etc/apt/sources.list.d/ubuntu-ports-${ARCHITECTURE}.list && \
	sed -i /etc/apt/sources.list \
	    -e "/^#/ d"  -e "/^$/ d" \
	    -e "s/^deb /deb [arch=amd64] /" && \
        cat /etc/apt/sources.list; \
    fi


######################################################################
# Package Master Builder Base Cross-builder image
#
# This image includes build dependencies and build configuration for a
# package.  While the Dockerfile is generic, it is configured to build
# package-specific images.

FROM builder_base_arch AS package_builder_arch

ARG DEBIAN_DIR=debian/
COPY ${DEBIAN_DIR} /tmp/build/debian/

RUN cd /tmp/build \
    && apt-get update \
    && if test $ARCHITECTURE != amd64; then \
        ARGS="--build-arch=$(dpkg-architecture -qDEB_BUILD_ARCH)"; \
        ARGS+=" --host-arch=${ARCHITECTURE}"; \
    fi \
    && yes "" | mk-build-deps -ir ${ARGS} ./debian/control \
    && apt-get clean
