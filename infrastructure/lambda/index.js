/**
 * TAG Video Systems - Telemetry Processor Lambda
 * Processes telemetry from SQS and evaluates probe health
 */
const { DynamoDBClient } = require("@aws-sdk/client-dynamodb");
const { DynamoDBDocumentClient, PutCommand } = require("@aws-sdk/lib-dynamodb");

const client = new DynamoDBClient({});
const ddb = DynamoDBDocumentClient.from(client);

const TABLE_NAME = process.env.TABLE_NAME;

exports.handler = async (event) => {
  console.log("Processing batch:", JSON.stringify(event, null, 2));

  const results = [];

  for (const record of event.Records) {
    try {
      // Parse the telemetry payload
      const payload = JSON.parse(record.body);
      console.log("Processing telemetry:", payload);

      // Validate required fields
      if (!payload.ProbeID || payload.FPS === undefined) {
        console.error("Invalid payload - missing required fields:", payload);
        continue;
      }

      // Evaluate health status based on FPS
      const status = payload.FPS >= 25 ? "HEALTHY" : "NOT_HEALTHY";
      const color = status === "HEALTHY" ? "green" : "red";

      // Prepare DynamoDB item
      const item = {
        ProbeID: payload.ProbeID,
        Status: status,
        Color: color,
        FPS: payload.FPS,
        Resolution: payload.Resolution || "unknown",
        Timestamp: payload.Timestamp || new Date().toISOString(),
        LastUpdated: new Date().toISOString(),
      };

      // Write to DynamoDB
      await ddb.send(
        new PutCommand({
          TableName: TABLE_NAME,
          Item: item,
        })
      );

      console.log(`✓ Updated ${payload.ProbeID}: ${status} (FPS: ${payload.FPS})`);
      results.push({ success: true, probeId: payload.ProbeID });
    } catch (error) {
      console.error("Error processing record:", error);
      results.push({ success: false, error: error.message });
    }
  }

  return {
    statusCode: 200,
    body: JSON.stringify({
      processed: results.length,
      results,
    }),
  };
};
