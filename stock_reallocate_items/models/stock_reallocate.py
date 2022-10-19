# -*- coding: utf-8 -*-
# Part of Odoo. See LICENSE file for full copyright and licensing details.

from odoo import models, fields, tools, api, _
from odoo.exceptions import UserError, ValidationError
from odoo.tools.float_utils import float_compare, float_is_zero


class StockReallocate(models.Model):
    _name = 'stock.reallocate'
    _inherit = ['mail.thread']
    _description = "Stock Reallocate"
    _order = "name desc, id desc"

    def _get_picking_out(self):
        company = self.env.company
        pick_out = self.env['stock.picking.type'].search([('warehouse_id.company_id', '=', company.id),
                                                             ('code', '=', 'outgoing')], limit=1,)
        return pick_out

    state = fields.Selection([
        ('draft', 'Draft'),
        ('confirm', 'Confirm'),
        ('wait', 'Waiting to approve'),
        ('done', 'Done'),
        ('cancel', 'Cancelled'),
    ], string='Status', readonly=True, copy=False, index=True, tracking=5, default='draft')
    name = fields.Char(string='Reallocate Reference', tracking=1, required=True, copy=False, readonly=True, index=True, default=lambda self: _('New'))
    picking_type_id = fields.Many2one('stock.picking.type', default=_get_picking_out, string='Operation Type', required=True, tracking=2)
    location_id = fields.Many2one('stock.location', string='Source location', required=True, tracking=3)
    company_id = fields.Many2one('res.company', 'Company', required=True, index=True,
                                 default=lambda self: self.env.company)
    product_id = fields.Many2one('product.product', string='Product', tracking=4, copy=False, required=True)
    qty_on_hand = fields.Float('Available', default=0.0, digits='Product Unit of Measure', compute='_compute_available_quantity')
    product_uom_id = fields.Many2one('uom.uom', 'Unit of Measure', copy=False)
    reallocate_line = fields.One2many('stock.reallocate.line', 'reallocate_id', string='Reallocate Lines',
                                      states={'cancel': [('readonly', True)], 'done': [('readonly', True)]}, copy=False,
                                      auto_join=True)

    @api.model
    def create(self, vals):
        if vals.get('name', _('New')) == _('New'):
            vals['name'] = self.env['ir.sequence'].next_by_code('stock.reallocate') or _('New')
        
        return super(StockReallocate, self).create(vals)

    def unlink(self):
        for obj in self:
            if obj.state not in ['cancel']:
                raise UserError(_('You cannot delete an order which is in %s state.') % ('cancel'))

        return super(StockReallocate, self).unlink()

    @api.onchange('product_id')
    def onchange_product(self):
        if not self.product_id:
            return

        self.product_uom_id = self.product_id.uom_id.id

    @api.onchange('location_id', 'product_id', 'picking_type_id')
    def onchange_operations(self):
        if not self.location_id or not self.product_id or not self.picking_type_id:
            return

        move_lines = self.env['stock.move'].search([('picking_id.picking_type_id', '=', self.picking_type_id.id),
                                                    ('location_id', '=', self.location_id.id),
                                                    ('product_id', '=', self.product_id.id),
                                                    ('state', 'in', ['confirmed', 'assigned', 'partially_available'])
                                                    ])
        reallocate_line = []
        for move in move_lines:
            if move.move_line_ids:
                for line in move.move_line_ids:
                    reallocate_line_data = self._prepare_move_line_reallocate(line)
                    reallocate_line += [(0, 0, reallocate_line_data)]
            else:
                reallocate_line_data = self._prepare_move_reallocate(move)
                reallocate_line += [(0, 0, reallocate_line_data)]

        if self.reallocate_line:
            self.reallocate_line.unlink()
        self.update({'reallocate_line': reallocate_line})

    @api.depends('location_id', 'product_id')
    def _compute_available_quantity(self):
        if not self.location_id or not self.product_id:
            self.qty_on_hand = 0.0
        else:
            self.qty_on_hand = self._get_available_quantity()

    def _prepare_move_reallocate(self, move):
        reallocate_line_data = {
            'picking_id': move.picking_id.id,
            'move_id': move.id,
            'product_id': move.product_id.id,
            'product_uom_id': move.product_uom.id,
            'qty_demand': move.product_uom_qty,
            'qty_reserved': move.reserved_availability,
            'qty_commit': move.reserved_availability,
        }

        return reallocate_line_data

    def _prepare_move_line_reallocate(self, line):
        reallocate_line_data = {
            'picking_id': line.picking_id.id,
            'move_id': line.move_id.id,
            'move_line_id': line.id,
            'product_id': line.product_id.id,
            'product_uom_id': line.product_uom_id.id,
            'qty_demand': line.move_id.product_uom_qty,
            'qty_reserved': line.product_uom_qty,
            'qty_done': line.qty_done,
            'qty_commit': line.product_uom_qty,
        }

        return reallocate_line_data

    def _get_available_quantity(self):
        quants = self.env['stock.quant'].sudo()._gather(self.product_id, self.location_id)
        rounding = self.product_id.uom_id.rounding
        if self.product_id.tracking == 'none':
            available_quantity = sum(quants.mapped('quantity'))
            return available_quantity if float_compare(available_quantity, 0.0,  precision_rounding=rounding) >= 0.0 else 0.0

    @api.constrains('reallocate_line')
    def check_available_quantity(self):
        qty_on_hand = self.qty_on_hand
        qty_commit = sum(self.reallocate_line.mapped('qty_commit'))

        if qty_on_hand < qty_commit:
            raise UserError(_("Shouldn't more than available quantity"))

    def action_confirm(self):
        if not self.reallocate_line:
            raise UserError(_("Product hasn't movement in waiting or ready."))

        qty_on_hand = self._get_available_quantity()
        self.qty_on_hand = qty_on_hand

        total_qty_commit = sum(self.reallocate_line.mapped('qty_commit'))
        if qty_on_hand < total_qty_commit:
            raise UserError(_("Should be less than available quantity."))

        if self.user_has_groups('stock_reallocate_items.group_stock_reallocate'):
            self.action_approve()
            return self.write({'state': 'done'})

        return self.write({'state': 'wait'})

    def action_approve(self):
        for line in self.reallocate_line:
            move = line.move_id
            if move.state not in ('confirmed', 'assigned', 'partially_available'):
                raise UserError(_('Please check Transfer.'))
            line.qty_reserved = move.reserved_availability
            move._do_unreserve()

        for line in self.reallocate_line.sorted(key=lambda r: r.qty_commit, reverse=True):
            move = line.move_id
            msg = "<b>" + _("The reserved quantity has been updated from %s.", line.reallocate_id.name) + "</b><ul>"
            msg += "<li> %s: <br/>" % line.product_id.display_name
            msg += _("Quantity: %s -> %s", line.qty_reserved, line.qty_commit) + "<br/>"
            msg += "</ul>"
            move.picking_id.message_post(body=msg)
            if line.qty_commit:
                move.with_context(qty_need=line.qty_commit)._action_assign()
            if move.move_line_ids:
                move.move_line_ids[0].update({'qty_done': move.reserved_availability})
            line.qty_reserved = move.reserved_availability
            line.qty_done = move.reserved_availability

    def action_cancel(self):
        return self.write({'state': 'cancel'})

    def action_draft(self):
        orders = self.filtered(lambda s: s.state in ['cancel'])
        return orders.write({
            'state': 'draft'
        })


class StockReallocateLine(models.Model):
    _name = 'stock.reallocate.line'
    _description = "Stock Reallocate line"

    reallocate_id = fields.Many2one('stock.reallocate', string='Reallocate', required=True, ondelete='cascade', index=True, copy=False)
    company_id = fields.Many2one(related='reallocate_id.company_id', string='Company', store=True, index=True)
    state = fields.Selection(related='reallocate_id.state', string='Reallocate Status', copy=False, store=True)
    picking_id = fields.Many2one('stock.picking', string='Transfer', check_company=True)
    move_id = fields.Many2one('stock.move', string='Stock Move', check_company=True)
    move_line_id = fields.Many2one('stock.move.line', string='Stock Move Line', check_company=True)
    origin = fields.Char(related='move_id.origin', string='Source Document')
    product_id = fields.Many2one('product.product', string='Product', domain="[('sale_ok', '=', True), '|', ('company_id', '=', False), ('company_id', '=', company_id)]", change_default=True, ondelete='restrict', check_company=True)
    product_uom_id = fields.Many2one('uom.uom', 'Unit of Measure', required=True)
    qty_demand = fields.Float('Demand', default=0.0, digits='Product Unit of Measure', required=True, copy=False)
    qty_reserved = fields.Float('Reserved', default=0.0, digits='Product Unit of Measure', required=True, copy=False)
    qty_done = fields.Float('Done', default=0.0, digits='Product Unit of Measure', copy=False)
    qty_commit = fields.Float('Commit', default=0.0, digits='Product Unit of Measure', copy=False)

    @api.onchange('qty_commit')
    def onchange_qty_commit(self):
        if self.qty_demand < self.qty_commit:
            raise UserError(_("Shouldn't more than demand quantity"))

        qty_on_hand = self.reallocate_id.qty_on_hand
        if qty_on_hand < self.qty_commit:
            raise UserError(_("Shouldn't more than available quantity"))


class StockMove(models.Model):
    _inherit = 'stock.move'

    def _update_reserved_quantity(self, need, available_quantity, location_id, lot_id=None, package_id=None, owner_id=None, strict=True):
        """ Create or update move lines.
        """
        qty_need = need
        if self.env.context.get('qty_need'):
            qty_need = self.env.context.get('qty_need')
        return super(StockMove, self)._update_reserved_quantity(qty_need, available_quantity, location_id, lot_id=lot_id, package_id=package_id, owner_id=owner_id, strict=strict)