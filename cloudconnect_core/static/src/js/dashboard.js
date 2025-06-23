/** @odoo-module **/

import { registry } from "@web/core/registry";
import { Component, useState, onWillStart, useSubEnv } from "@odoo/owl";
import { useService } from "@web/core/utils/hooks";
import { _t } from "@web/core/l10n/translation";

export class CloudConnectDashboard extends Component {
    static template = "cloudconnect_core.Dashboard";
    static props = {};

    setup() {
        this.rpc = useService("rpc");
        this.action = useService("action");
        this.notification = useService("notification");
        
        this.state = useState({
            isLoading: true,
            stats: {
                configs: 0,
                properties: 0,
                webhooks: 0,
                errors: 0,
            },
            recentLogs: [],
            syncStats: {},
            webhookStats: {},
        });

        onWillStart(async () => {
            await this.loadDashboardData();
        });
    }

    async loadDashboardData() {
        try {
            // Load statistics
            const [configData, propertyData, webhookData, logData] = await Promise.all([
                this.rpc("/web/dataset/search_count", {
                    model: "cloudconnect.config",
                    domain: [["active", "=", true]],
                }),
                this.rpc("/web/dataset/search_count", {
                    model: "cloudconnect.property",
                    domain: [["sync_enabled", "=", true]],
                }),
                this.rpc("/web/dataset/search_count", {
                    model: "cloudconnect.webhook",
                    domain: [["active", "=", true]],
                }),
                this.rpc("/web/dataset/search_count", {
                    model: "cloudconnect.sync.log",
                    domain: [
                        ["status", "=", "error"],
                        ["sync_date", ">=", this.getLast24Hours()],
                    ],
                }),
            ]);

            // Load recent logs
            const recentLogs = await this.rpc("/web/dataset/search_read", {
                model: "cloudconnect.sync.log",
                fields: ["sync_date", "operation_type", "model_name", "status", "summary"],
                limit: 10,
                order: "sync_date desc",
            });

            // Load sync statistics
            const syncStats = await this.rpc("/web/dataset/call_kw", {
                model: "cloudconnect.sync.log",
                method: "get_dashboard_stats",
                args: [24],
                kwargs: {},
            });

            this.state.stats = {
                configs: configData,
                properties: propertyData,
                webhooks: webhookData,
                errors: logData,
            };
            this.state.recentLogs = recentLogs;
            this.state.syncStats = syncStats;
            this.state.isLoading = false;

        } catch (error) {
            console.error("Error loading dashboard data:", error);
            this.notification.add(_t("Error loading dashboard data"), {
                type: "danger",
            });
            this.state.isLoading = false;
        }
    }

    getLast24Hours() {
        const date = new Date();
        date.setHours(date.getHours() - 24);
        return date.toISOString().split('T')[0];
    }

    async onClickTestConnection() {
        const configs = await this.rpc("/web/dataset/search_read", {
            model: "cloudconnect.config",
            fields: ["id"],
            domain: [["active", "=", true]],
            limit: 1,
        });

        if (configs.length > 0) {
            await this.rpc("/web/dataset/call_kw", {
                model: "cloudconnect.config",
                method: "action_test_connection",
                args: [[configs[0].id]],
                kwargs: {},
            });
        } else {
            this.notification.add(_t("No active configuration found"), {
                type: "warning",
            });
        }
    }

    onClickViewProperties() {
        this.action.doAction("cloudconnect_core.action_cloudconnect_property");
    }

    onClickViewWebhooks() {
        this.action.doAction("cloudconnect_core.action_cloudconnect_webhook");
    }

    onClickViewLogs() {
        this.action.doAction("cloudconnect_core.action_cloudconnect_sync_log");
    }

    onClickViewErrors() {
        this.action.doAction("cloudconnect_core.action_cloudconnect_sync_errors");
    }

    onClickSetupWizard() {
        this.action.doAction("cloudconnect_core.action_cloudconnect_setup_wizard");
    }

    getStatusClass(status) {
        const statusClasses = {
            success: "text-success",
            error: "text-danger",
            warning: "text-warning",
            pending: "text-muted",
        };
        return statusClasses[status] || "text-muted";
    }

    getStatusIcon(status) {
        const statusIcons = {
            success: "fa-check-circle",
            error: "fa-times-circle",
            warning: "fa-exclamation-triangle",
            pending: "fa-clock-o",
        };
        return statusIcons[status] || "fa-question-circle";
    }

    formatDate(dateStr) {
        if (!dateStr) return "";
        const date = new Date(dateStr);
        return date.toLocaleString();
    }
}

CloudConnectDashboard.template = xml`
<div class="o_cloudconnect_dashboard">
    <div class="container-fluid">
        <div class="row">
            <div class="col-12">
                <h1 class="mb-4">CloudConnect Dashboard</h1>
            </div>
        </div>
        
        <div t-if="state.isLoading" class="text-center">
            <i class="fa fa-spinner fa-spin fa-3x"/>
            <p>Loading dashboard data...</p>
        </div>
        
        <div t-else="">
            <!-- Statistics Cards -->
            <div class="row mb-4">
                <div class="col-md-3">
                    <div class="card text-center">
                        <div class="card-body">
                            <i class="fa fa-cog fa-3x text-primary mb-3"/>
                            <h5 class="card-title">Configurations</h5>
                            <h2 class="text-primary" t-esc="state.stats.configs"/>
                        </div>
                    </div>
                </div>
                
                <div class="col-md-3">
                    <div class="card text-center">
                        <div class="card-body">
                            <i class="fa fa-building fa-3x text-success mb-3"/>
                            <h5 class="card-title">Active Properties</h5>
                            <h2 class="text-success" t-esc="state.stats.properties"/>
                        </div>
                    </div>
                </div>
                
                <div class="col-md-3">
                    <div class="card text-center">
                        <div class="card-body">
                            <i class="fa fa-plug fa-3x text-info mb-3"/>
                            <h5 class="card-title">Active Webhooks</h5>
                            <h2 class="text-info" t-esc="state.stats.webhooks"/>
                        </div>
                    </div>
                </div>
                
                <div class="col-md-3">
                    <div class="card text-center">
                        <div class="card-body">
                            <i class="fa fa-exclamation-triangle fa-3x text-danger mb-3"/>
                            <h5 class="card-title">Recent Errors</h5>
                            <h2 class="text-danger" t-esc="state.stats.errors"/>
                        </div>
                    </div>
                </div>
            </div>
            
            <!-- Quick Actions -->
            <div class="row mb-4">
                <div class="col-12">
                    <h3>Quick Actions</h3>
                    <div class="btn-group" role="group">
                        <button class="btn btn-primary" t-on-click="onClickTestConnection">
                            <i class="fa fa-refresh"/> Test Connection
                        </button>
                        <button class="btn btn-secondary" t-on-click="onClickViewProperties">
                            <i class="fa fa-building"/> Properties
                        </button>
                        <button class="btn btn-secondary" t-on-click="onClickViewWebhooks">
                            <i class="fa fa-plug"/> Webhooks
                        </button>
                        <button class="btn btn-secondary" t-on-click="onClickViewLogs">
                            <i class="fa fa-history"/> Logs
                        </button>
                        <button class="btn btn-info" t-on-click="onClickSetupWizard">
                            <i class="fa fa-magic"/> Setup Wizard
                        </button>
                    </div>
                </div>
            </div>
            
            <!-- Recent Activity -->
            <div class="row">
                <div class="col-md-8">
                    <div class="card">
                        <div class="card-header">
                            <h4>Recent Activity</h4>
                        </div>
                        <div class="card-body">
                            <div t-if="!state.recentLogs.length" class="text-muted text-center">
                                <p>No recent activity</p>
                            </div>
                            <ul t-else="" class="list-unstyled">
                                <li t-foreach="state.recentLogs" t-as="log" t-key="log.id" class="mb-2">
                                    <i t-att-class="'fa ' + getStatusIcon(log.status) + ' ' + getStatusClass(log.status)"/>
                                    <span class="ml-2" t-esc="formatDate(log.sync_date)"/>
                                    <span class="ml-2 font-weight-bold" t-esc="log.operation_type"/>
                                    <span class="ml-1" t-esc="log.model_name"/>
                                    <div class="small text-muted ml-4" t-esc="log.summary"/>
                                </li>
                            </ul>
                        </div>
                    </div>
                </div>
                
                <div class="col-md-4">
                    <div class="card">
                        <div class="card-header">
                            <h4>Sync Statistics</h4>
                        </div>
                        <div class="card-body">
                            <div t-if="state.syncStats.total">
                                <p>Total syncs: <strong t-esc="state.syncStats.total"/></p>
                                <p>Successful: <strong class="text-success" t-esc="state.syncStats.success"/></p>
                                <p>Errors: <strong class="text-danger" t-esc="state.syncStats.error"/></p>
                                <p>Warnings: <strong class="text-warning" t-esc="state.syncStats.warning"/></p>
                                <hr/>
                                <h5>Recent Errors:</h5>
                                <ul t-if="state.syncStats.recent_errors" class="small">
                                    <li t-foreach="state.syncStats.recent_errors" t-as="error" t-key="error.id">
                                        <strong t-esc="error.model"/>: <span t-esc="error.error"/>
                                    </li>
                                </ul>
                                <button t-if="state.stats.errors > 0" 
                                        class="btn btn-sm btn-danger mt-2" 
                                        t-on-click="onClickViewErrors">
                                    View All Errors
                                </button>
                            </div>
                            <div t-else="" class="text-muted text-center">
                                <p>No sync data available</p>
                            </div>
                        </div>
                    </div>
                </div>
            </div>
        </div>
    </div>
</div>
`;

registry.category("actions").add("cloudconnect_dashboard", CloudConnectDashboard);