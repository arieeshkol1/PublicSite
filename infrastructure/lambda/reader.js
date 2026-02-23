const AWS = require('aws-sdk');
const dynamodb = new AWS.DynamoDB.DocumentClient();

exports.handler = async (event) => {
    const tableName = process.env.METRICS_TABLE;
    
    // Get the latest metrics for each type
    const metricTypes = [
        'SECURITY_THREATS',
        'OPERATIONAL_HEALTH',
        'COST_OPTIMIZATION',
        'MULTI_REGION',
        'WAF_DETAILS',
        'PATCH_MANAGEMENT',
        'INCIDENT_RESPONSE'
    ];
    
    try {
        const queryPromises = metricTypes.map(async (metricType) => {
            const result = await dynamodb.query({
                TableName: tableName,
                KeyConditionExpression: 'metricType = :mt',
                ExpressionAttributeValues: {
                    ':mt': metricType
                },
                ScanIndexForward: false, // Sort descending by timestamp
                Limit: 1
            }).promise();
            
            return result.Items[0] || null;
        });
        
        const metrics = await Promise.all(queryPromises);
        const metricsMap = {};
        
        metrics.forEach(metric => {
            if (metric) {
                metricsMap[metric.metricType] = metric;
            }
        });
        
        return {
            statusCode: 200,
            headers: {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*',
                'Cache-Control': 'no-cache'
            },
            body: JSON.stringify({
                success: true,
                timestamp: Date.now(),
                metrics: metricsMap
            })
        };
    } catch (error) {
        console.error('Error reading metrics:', error);
        return {
            statusCode: 500,
            headers: {
                'Content-Type': 'application/json',
                'Access-Control-Allow-Origin': '*'
            },
            body: JSON.stringify({
                success: false,
                error: 'Failed to read metrics',
                details: error.message
            })
        };
    }
};
