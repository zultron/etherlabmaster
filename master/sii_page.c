/*****************************************************************************
 *
 *  Copyright (C) 2026  Florian Pose, Ingenieurgemeinschaft IgH
 *
 *  This file is part of the IgH EtherCAT Master.
 *
 *  The IgH EtherCAT Master is free software; you can redistribute it and/or
 *  modify it under the terms of the GNU General Public License version 2, as
 *  published by the Free Software Foundation.
 *
 *  The IgH EtherCAT Master is distributed in the hope that it will be useful,
 *  but WITHOUT ANY WARRANTY; without even the implied warranty of
 *  MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the GNU General
 *  Public License for more details.
 *
 *  You should have received a copy of the GNU General Public License along
 *  with the IgH EtherCAT Master; if not, write to the Free Software
 *  Foundation, Inc., 51 Franklin St, Fifth Floor, Boston, MA  02110-1301  USA
 *
 ****************************************************************************/

/**
   \file
   EtherCAT SII page methods.
*/

/****************************************************************************/

#include "sii_page.h"

#include <linux/slab.h>

/****************************************************************************/

/**
   SII page constructor.
*/

void ec_sii_page_init(
        ec_sii_page_t *page /**< SII page. */
        )
{
    page->vendor_id = 0x00000000;
    page->product_code = 0x00000000;
    page->revision_number = 0x00000000;
    page->serial_number = 0x00000000;
    page->alias = 0x0000;

    page->origin = EC_SII_PAGE_UNKNOWN;

    page->words = NULL;
    page->word_count = 0;
}

/****************************************************************************/

/**
   Slave destructor.
   Clears and frees a page object.
*/

void ec_sii_page_clear(
        ec_sii_page_t *page /**< SII page. */
        )
{
    if (page->words) {
        kfree(page->words);
    }
}

/****************************************************************************/

/**
 * Free page memory.
 */
int ec_sii_page_alloc(
        ec_sii_page_t *page, /**< SII page. */
        size_t word_count /**< Number of words to allocate. */
        )
{
    if (page->words) {
        kfree(page->words);
    }

    page->word_count = 0;

    if (!(page->words = (uint16_t *) kmalloc(word_count * 2, GFP_KERNEL))) {
        return -ENOMEM;
    }

    page->word_count = word_count;
    return 0;
}

/****************************************************************************/
