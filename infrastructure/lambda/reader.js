/**
 * TAG Video Systems - Probe Reader Lambda
 * Reads current status of all probes from DynamoDB
 */
const { DynamoDBClient, ScanCommand } = require("@aws-sdk/client-dynamodb");
const { unmarshall } = require("@aws-sdk/util-dynamodb");

const client = new DynamoDBClient({});
const TABLE_NAME = process.env.TABLE_NAME;

exports.handler = async (event) => {
  console.log("Reading probe status...");

  try {
    // Scan DynamoDB table for all probes
    const response = await client.send(
      new ScanCommand({
        TableName: TABLE_NAME,
      })
    );

    // Convert DynamoDB format to plain JSON
    const probes = response.Items.map((item) => unmarshall(item));

    console.log(`Found ${probes.length} probes`);

    return {
      statusCode: 200,
      headers: {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
        "Access-Control-Allow-Headers": "Content-Type",
        "Access-Control-Allow-Methods": "GET,OPTIONS",
      },
      body: JSON.stringify({
        probes,
        count: probes.length,
        timestamp: new Date().toISOString(),
      }),
    };
  } catch (error) {
    console.error("Error reading probes:", error);

    return {
      statusCode: 500,
      headers: {
        "Content-Type": "application/json",
        "Access-Control-Allow-Origin": "*",
      },
      body: JSON.stringify({
        error: "Failed to read probe status",
        message: error.message,
      }),
    };
  }
};
