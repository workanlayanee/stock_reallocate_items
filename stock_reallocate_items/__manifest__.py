# -*- coding: utf-8 -*-
#############################################################################
#
#    K. Kanlayanee Panpiriya
#
#    Copyright (C) 2022-TODAY Kanlayanee Panpiriya(<workanlayanee@gmail.com>)
#    Author: Kanlayanee Panpiriya(<workanlayanee@gmail.com>)
#
#    You can modify it under the terms of the GNU LESSER
#    GENERAL PUBLIC LICENSE (LGPL v3), Version 3.
#
#    This program is distributed in the hope that it will be useful,
#    but WITHOUT ANY WARRANTY; without even the implied warranty of
#    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
#    GNU LESSER GENERAL PUBLIC LICENSE (LGPL v3) for more details.
#
#    You should have received a copy of the GNU LESSER GENERAL PUBLIC LICENSE
#    (LGPL v3) along with this program.
#    If not, see <http://www.gnu.org/licenses/>.
#
#############################################################################

{
    "name": "Stock Reallocate Items",
    "description": "commutate several products in each order easily.",
    "summary": "commit product for change several reserved",
    "category": "Inventory/Inventory",
    "version": "15.0.1.0",
    "author": 'Kanlayanee Panpiriya',
    "support": "workanlayanee@gmail.com",
    "price": 49.0,
    "currency": 'EUR',
    "depends": ['stock'],
    "data": [

        'data/ir_sequence_data.xml',
        'security/ir.model.access.csv',
        'security/stock_reallocate_security.xml',
        'views/stock_reallocate_view.xml',

    ],
    'license': 'LGPL-3',
    'installable': True,
    'application': True,
    'auto_install': False,
}
