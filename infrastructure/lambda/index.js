const AWS = require('aws-sdk');
const dynamodb = new AWS.DynamoDB.DocumentClient();

// Simulate realistic operational metrics for Made4Net Fortress & Factory
exports.handler = async (event) => {
    const tableName = process.env.METRICS_TABLE;
    const timestamp = Date.now();
    
    // Generate realistic metrics
    const metrics = [
        // Security Metrics
        {
            metricType: 'SECURITY_THREATS',
            timestamp: timestamp,
            value: Math.floor(Math.random() * 5), // 0-5 threats detected
            details: {
                guardDutyFindings: Math.floor(Math.random() * 3),
                wafBlockedRequests: Math.floor(Math.random() * 50) + 100,
                failedAuthAttempts: Math.floor(Math.random() * 10),
                encryptionCoverage: 100, // Always 100% in compliant environment
                complianceScore: Math.floor(Math.random() * 5) + 95 // 95-100
            }
        },
        // Operational Health
        {
            metricType: 'OPERATIONAL_HEALTH',
            timestamp: timestamp,
            value: Math.random() * 0.01 + 99.99, // 99.99-100% availability
            details: {
                availability: (Math.random() * 0.01 + 99.99).toFixed(4),
                patchCompliance: Math.floor(Math.random() * 5) + 95, // 95-100%
                canarySuccessRate: (Math.random() * 0.5 + 99.5).toFixed(2),
                mttrMinutes: Math.floor(Math.random() * 10) + 5, // 5-15 minutes
                activeServers: Math.floor(Math.random() * 20) + 180 // 180-200 servers
            }
        },
        // Cost Optimization
        {
            metricType: 'COST_OPTIMIZATION',
            timestamp: timestamp,
            value: Math.floor(Math.random() * 5000) + 15000, // $15k-$20k monthly savings
            details: {
                monthlySavings: Math.floor(Math.random() * 5000) + 15000,
                idleResources: Math.floor(Math.random() * 5),
                schedulerSavings: Math.floor(Math.random() * 3000) + 7000,
                trustedAdvisorRecommendations: Math.floor(Math.random() * 3) + 2,
                costReductionPercent: 30 // Target 30% reduction
            }
        },
        // Multi-Region Status
        {
            metricType: 'MULTI_REGION',
            timestamp: timestamp,
            value: 1, // 1 = healthy, 0 = degraded
            details: {
                primaryRegion: 'us-east-1',
                primaryStatus: 'ACTIVE',
                drRegion: 'us-west-2',
                drStatus: 'STANDBY',
                replicationLagMs: Math.floor(Math.random() * 100) + 50, // 50-150ms
                lastFailoverTest: Date.now() - (7 * 24 * 60 * 60 * 1000) // 7 days ago
            }
        },
        // WAF Metrics (detailed)
        {
            metricType: 'WAF_DETAILS',
            timestamp: timestamp,
            value: Math.floor(Math.random() * 50) + 100,
            details: {
                sqlInjectionBlocked: Math.floor(Math.random() * 20) + 30,
                xssBlocked: Math.floor(Math.random() * 15) + 20,
                geoBlocked: Math.floor(Math.random() * 30) + 40,
                rateLimitExceeded: Math.floor(Math.random() * 10) + 5,
                totalBlocked: Math.floor(Math.random() * 50) + 100
            }
        },
        // Patch Management
        {
            metricType: 'PATCH_MANAGEMENT',
            timestamp: timestamp,
            value: Math.floor(Math.random() * 5) + 95,
            details: {
                totalServers: 200,
                compliantServers: Math.floor(Math.random() * 10) + 190,
                pendingPatches: Math.floor(Math.random() * 10),
                criticalPatchesPending: Math.floor(Math.random() * 2),
                nextMaintenanceWindow: Date.now() + (2 * 24 * 60 * 60 * 1000), // 2 days from now
                lastPatchRun: Date.now() - (3 * 24 * 60 * 60 * 1000) // 3 days ago
            }
        },
        // Incident Response
        {
            metricType: 'INCIDENT_RESPONSE',
            timestamp: timestamp,
            value: Math.floor(Math.random() * 3), // 0-3 active incidents
            details: {
                activeIncidents: Math.floor(Math.random() * 3),
                resolvedToday: Math.floor(Math.random() * 5) + 2,
                avgResolutionTimeMin: Math.floor(Math.random() * 10) + 8,
                p1Incidents: 0, // Critical incidents
                p2Incidents: Math.floor(Math.random() * 2),
                p3Incidents: Math.floor(Math.random() * 3)
            }
        }
    ];
    
    // Write all metrics to DynamoDB
    const putPromises = metrics.map(metric => {
        return dynamodb.put({
            TableName: tableName,
            Item: metric
        }).promise();
    });
    
    try {
        await Promise.all(putPromises);
        
        return {
            statusCode: 200,
            headers: {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            body: JSON.stringify({
                message: 'Metrics generated successfully',
                timestamp: timestamp,
                metricsCount: metrics.length
            })
        };
    } catch (error) {
        console.error('Error writing metrics:', error);
        return {
            statusCode: 500,
            headers: {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            body: JSON.stringify({
                error: 'Failed to generate metrics',
                details: error.message
            })
        };
    }
};
