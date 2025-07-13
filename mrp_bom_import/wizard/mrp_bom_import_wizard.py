# -*- coding: utf-8 -*-

import base64
import csv
import io
from odoo import models, fields, api, _
from odoo.exceptions import UserError, ValidationError


class MrpBomImportWizard(models.TransientModel):
    _name = 'mrp.bom.import.wizard'
    _description = 'Import Bill of Materials Wizard'

    file_data = fields.Binary(
        string='CSV File',
        required=True,
        help='Select CSV file to import Bill of Materials'
    )
    file_name = fields.Char(string='File Name')
    delimiter = fields.Selection([
        (',', 'Comma (,)'),
        (';', 'Semicolon (;)'),
        ('|', 'Pipe (|)'),
        ('\t', 'Tab'),
    ], string='Delimiter', default=',', required=True)
    
    # Campos para mostrar resultados
    state = fields.Selection([
        ('draft', 'Draft'),
        ('done', 'Done'),
        ('error', 'Error')
    ], default='draft')
    result_message = fields.Text(string='Import Results', readonly=True)
    error_message = fields.Text(string='Errors', readonly=True)
    imported_count = fields.Integer(string='Imported BoMs', readonly=True)

    @api.constrains('file_name')
    def _check_file_name(self):
        for record in self:
            if record.file_name and not record.file_name.lower().endswith('.csv'):
                raise ValidationError(_('Please upload only CSV files.'))

    def action_import(self):
        """Main method to import BoMs from CSV file"""
        self.ensure_one()
        
        if not self.file_data:
            raise UserError(_('Please select a CSV file to import.'))
        
        # Decode file
        try:
            csv_data = base64.b64decode(self.file_data)
            csv_file = io.StringIO(csv_data.decode('utf-8'))
            csv_reader = csv.DictReader(csv_file, delimiter=self.delimiter)
        except Exception as e:
            raise UserError(_('Error reading CSV file: %s') % str(e))
        
        # Process CSV
        imported_boms = []
        errors = []
        bom_data = {}
        current_bom_code = None
        
        for row_number, row in enumerate(csv_reader, start=2):
            try:
                # Validate required fields
                if not row.get('bom_code'):
                    errors.append(_('Row %d: BoM code is required') % row_number)
                    continue
                
                # Si es una nueva BoM
                if row.get('product_code'):
                    # Procesar BoM anterior si existe
                    if current_bom_code and current_bom_code in bom_data:
                        result = self._create_bom(bom_data[current_bom_code])
                        if result.get('success'):
                            imported_boms.append(result['bom'])
                        else:
                            errors.append(result['error'])
                    
                    # Iniciar nueva BoM
                    current_bom_code = row['bom_code']
                    bom_data[current_bom_code] = {
                        'code': current_bom_code,
                        'product_code': row['product_code'],
                        'product_qty': float(row.get('product_qty', 1.0)),
                        'product_uom': row.get('product_uom', ''),
                        'type': row.get('type', 'normal'),
                        'components': []
                    }
                
                # Agregar componente
                if row.get('component_code'):
                    if current_bom_code and current_bom_code in bom_data:
                        bom_data[current_bom_code]['components'].append({
                            'product_code': row['component_code'],
                            'qty': float(row.get('component_qty', 1.0)),
                            'uom': row.get('component_uom', ''),
                            'operation': row.get('operation_name', '')
                        })
                    
            except Exception as e:
                errors.append(_('Row %d: %s') % (row_number, str(e)))
        
        # Procesar última BoM
        if current_bom_code and current_bom_code in bom_data:
            result = self._create_bom(bom_data[current_bom_code])
            if result.get('success'):
                imported_boms.append(result['bom'])
            else:
                errors.append(result['error'])
        
        # Actualizar resultados
        if imported_boms:
            self.state = 'done'
            self.imported_count = len(imported_boms)
            self.result_message = _('Successfully imported %d Bill of Materials') % len(imported_boms)
        else:
            self.state = 'error'
            self.result_message = _('No Bill of Materials were imported')
        
        if errors:
            self.error_message = '\n'.join(errors[:50])  # Limitar a 50 errores
            if len(errors) > 50:
                self.error_message += _('\n... and %d more errors') % (len(errors) - 50)
        
        return {
            'type': 'ir.actions.act_window',
            'res_model': 'mrp.bom.import.wizard',
            'view_mode': 'form',
            'res_id': self.id,
            'target': 'new',
            'context': self.env.context,
        }

    def _create_bom(self, bom_info):
        """Create a BoM with its components"""
        try:
            # Buscar producto principal
            product = self._find_product(bom_info['product_code'])
            
            if not product:
                return {
                    'success': False,
                    'error': _('BoM %s: Product %s not found') % (bom_info['code'], bom_info['product_code'])
                }
            
            # Obtener UoM
            uom = self._get_uom(bom_info['product_uom'], product.uom_id)
            
            # Verificar si ya existe una BoM con este código
            existing_bom = self.env['mrp.bom'].search([('code', '=', bom_info['code'])], limit=1)
            if existing_bom:
                return {
                    'success': False,
                    'error': _('BoM with code %s already exists') % bom_info['code']
                }
            
            # Crear BoM
            bom_vals = {
                'code': bom_info['code'],
                'product_tmpl_id': product.product_tmpl_id.id,
                'product_id': product.id,
                'product_qty': bom_info['product_qty'],
                'product_uom_id': uom.id,
                'type': bom_info['type'] if bom_info['type'] in ['normal', 'phantom'] else 'normal',
                'bom_line_ids': []
            }
            
            # Procesar componentes
            for comp in bom_info['components']:
                comp_product = self._find_product(comp['product_code'])
                
                if not comp_product:
                    return {
                        'success': False,
                        'error': _('BoM %s: Component %s not found') % (bom_info['code'], comp['product_code'])
                    }
                
                comp_uom = self._get_uom(comp['uom'], comp_product.uom_id)
                
                line_vals = {
                    'product_id': comp_product.id,
                    'product_qty': comp['qty'],
                    'product_uom_id': comp_uom.id,
                }
                
                # Si hay operación especificada
                if comp['operation']:
                    operation = self.env['mrp.routing.workcenter'].search([
                        ('name', '=', comp['operation']),
                        ('bom_id', '=', False)  # Buscaremos operaciones plantilla
                    ], limit=1)
                    if operation:
                        line_vals['operation_id'] = operation.id
                
                bom_vals['bom_line_ids'].append((0, 0, line_vals))
            
            # Crear BoM
            bom = self.env['mrp.bom'].create(bom_vals)
            
            return {
                'success': True,
                'bom': bom
            }
            
        except Exception as e:
            return {
                'success': False,
                'error': _('BoM %s: %s') % (bom_info['code'], str(e))
            }

    def _get_uom(self, uom_name, default_uom):
        """Get UoM by name or return default"""
        if not uom_name:
            return default_uom
        
        uom = self.env['uom.uom'].search([('name', '=', uom_name)], limit=1)
        if not uom:
            # Buscar por nombre corto
            uom = self.env['uom.uom'].search([('name', 'ilike', uom_name)], limit=1)
        
        return uom or default_uom

    def action_view_boms(self):
        """Open BoMs list view"""
        return {
            'type': 'ir.actions.act_window',
            'name': _('Bills of Materials'),
            'res_model': 'mrp.bom',
            'view_mode': 'tree,form',
            'domain': [],
            'context': {'search_default_group_by_product': 1},
        }

    def action_download_template(self):
        """Download CSV template"""
        template_data = """bom_code,product_code,product_qty,product_uom,type,component_code,component_qty,component_uom,operation_name
BOM001,PROD001,1,Units,normal,COMP001,2,Units,
BOM001,,,,,,COMP002,1,Units,
BOM002,PROD002,1,Units,phantom,COMP003,5,Units,
BOM002,,,,,,COMP004,3,Units,"""
        
        data = base64.b64encode(template_data.encode('utf-8'))
        attachment = self.env['ir.attachment'].create({
            'name': 'bom_import_template.csv',
            'type': 'binary',
            'datas': data,
            'mimetype': 'text/csv',
        })
        
        return {
            'type': 'ir.actions.act_url',
            'url': '/web/content/%s?download=true' % attachment.id,
            'target': 'self',
        }