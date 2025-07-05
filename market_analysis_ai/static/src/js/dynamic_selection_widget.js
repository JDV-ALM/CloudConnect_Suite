/** @odoo-module **/

import { registry } from "@web/core/registry";
import { SelectField } from "@web/views/fields/selection/selection_field";
import { useService } from "@web/core/utils/hooks";

export class DynamicModelSelectionField extends SelectField {
    setup() {
        super.setup();
        this.orm = useService("orm");
    }
    
    async willStart() {
        await super.willStart();
        await this._updateOptions();
    }
    
    async _updateOptions() {
        if (this.props.record && this.props.record.data.id) {
            try {
                // Obtener los modelos disponibles del registro
                const fieldName = this.props.name === 'claude_model' ? 'available_claude_models' : 'available_openai_models';
                const modelsJson = this.props.record.data[fieldName];
                
                if (modelsJson) {
                    const models = JSON.parse(modelsJson);
                    // Actualizar las opciones del campo
                    this.options = models.map(m => [m.id, m.name || m.id]);
                }
            } catch (error) {
                console.error("Error al cargar modelos dinámicos:", error);
            }
        }
    }
    
    async onChange(value) {
        await super.onChange(value);
        // Actualizar las opciones cuando cambie el valor
        await this._updateOptions();
    }
}

DynamicModelSelectionField.template = "web.SelectionField";

registry.category("fields").add("dynamic_model_selection", DynamicModelSelectionField);