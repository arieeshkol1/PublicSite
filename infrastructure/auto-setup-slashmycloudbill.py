#!/usr/bin/env python3
"""
One-shot setup for slashmycloudbill.com
Run with: python infrastructure/auto-setup-slashmycloudbill.py

Uses your default AWS credentials (must have ACM + CloudFront + Route53 access).
Run: aws configure  (if not already configured with your personal credentials)
"""
import boto3, json, time, sys

DISTRIBUTION_ID = "E12JIHGHK40OLE"
CF_DOMAIN = "d13k71im98zj35.cloudfront.net"
HOSTED_ZONE_ID = "Z08610352PUNQ7MUZTRVI"
DOMAIN = "slashmycloudbill.com"
WWW = "www.slashmycloudbill.com"
REGION = "us-east-1"

acm = boto3.client("acm", region_name=REGION)
cf = boto3.client("cloudfront")
r53 = boto3.client("route53")

print("=== slashmycloudbill.com Auto-Setup ===\n")

# ── Step 1: Request certificate ───────────────────────────────────────────
print("1. Requesting SSL certificate...")
cert_resp = acm.request_certificate(
    DomainName=DOMAIN,
    SubjectAlternativeNames=[WWW],
    ValidationMethod="DNS",
    Tags=[{"Key": "Project", "Value": "SlashMyCloudBill"}]
)
cert_arn = cert_resp["CertificateArn"]
print(f"   Certificate ARN: {cert_arn}")

# ── Step 2: Get DNS validation records and add to Route 53 ────────────────
print("2. Adding DNS validation records to Route 53...")
time.sleep(8)  # Wait for ACM to generate validation records

for attempt in range(10):
    cert_detail = acm.describe_certificate(CertificateArn=cert_arn)
    dv_options = cert_detail["Certificate"].get("DomainValidationOptions", [])
    records = [dv["ResourceRecord"] for dv in dv_options if "ResourceRecord" in dv]
    if records:
        break
    print(f"   Waiting for validation records... ({attempt+1}/10)")
    time.sleep(5)

if not records:
    print("ERROR: Could not get validation records. Check ACM console.")
    sys.exit(1)

# Deduplicate (both domains often share the same CNAME)
seen = set()
changes = []
for rec in records:
    if rec["Name"] not in seen:
        seen.add(rec["Name"])
        changes.append({
            "Action": "UPSERT",
            "ResourceRecordSet": {
                "Name": rec["Name"],
                "Type": rec["Type"],
                "TTL": 300,
                "ResourceRecords": [{"Value": rec["Value"]}]
            }
        })
        print(f"   Adding CNAME: {rec['Name']}")

r53.change_resource_record_sets(
    HostedZoneId=HOSTED_ZONE_ID,
    ChangeBatch={"Changes": changes}
)
print("   DNS validation records added.")

# ── Step 3: Wait for certificate to be issued ─────────────────────────────
print("3. Waiting for certificate validation (2-5 minutes)...")
for i in range(60):
    status = acm.describe_certificate(CertificateArn=cert_arn)["Certificate"]["Status"]
    print(f"   Status: {status} ({i*5}s)", end="\r")
    if status == "ISSUED":
        print(f"\n   Certificate ISSUED!")
        break
    time.sleep(5)
else:
    print(f"\nERROR: Certificate not issued after 5 minutes. Status: {status}")
    print(f"Re-run this script later with CERT_ARN={cert_arn}")
    sys.exit(1)

# ── Step 4: Update CloudFront distribution ────────────────────────────────
print("4. Updating CloudFront distribution...")
dist_resp = cf.get_distribution_config(Id=DISTRIBUTION_ID)
etag = dist_resp["ETag"]
config = dist_resp["DistributionConfig"]

# Add aliases
items = config.get("Aliases", {}).get("Items", [])
for d in [DOMAIN, WWW]:
    if d not in items:
        items.append(d)
config["Aliases"] = {"Quantity": len(items), "Items": items}

# Set certificate
config["ViewerCertificate"] = {
    "ACMCertificateArn": cert_arn,
    "SSLSupportMethod": "sni-only",
    "MinimumProtocolVersion": "TLSv1.2_2021",
    "CloudFrontDefaultCertificate": False
}

cf.update_distribution(
    Id=DISTRIBUTION_ID,
    DistributionConfig=config,
    IfMatch=etag
)
print("   CloudFront updated with new domains and certificate.")

# ── Step 5: Create CloudFront Function ────────────────────────────────────
print("5. Creating CloudFront routing function...")
func_code = open("infrastructure/cf-function-slashmycloudbill.js", "r").read()

try:
    existing = cf.describe_function(Name="SlashMyCloudBill-Router")
    etag_fn = existing["ETag"]
    cf.update_function(
        Name="SlashMyCloudBill-Router",
        IfMatch=etag_fn,
        FunctionConfig={"Comment": "Routes slashmycloudbill.com", "Runtime": "cloudfront-js-2.0"},
        FunctionCode=func_code.encode()
    )
    etag_fn = cf.describe_function(Name="SlashMyCloudBill-Router")["ETag"]
    pub = cf.publish_function(Name="SlashMyCloudBill-Router", IfMatch=etag_fn)
except cf.exceptions.NoSuchFunctionExists:
    cf.create_function(
        Name="SlashMyCloudBill-Router",
        FunctionConfig={"Comment": "Routes slashmycloudbill.com", "Runtime": "cloudfront-js-2.0"},
        FunctionCode=func_code.encode()
    )
    etag_fn = cf.describe_function(Name="SlashMyCloudBill-Router")["ETag"]
    pub = cf.publish_function(Name="SlashMyCloudBill-Router", IfMatch=etag_fn)

func_arn = pub["FunctionSummary"]["FunctionMetadata"]["FunctionARN"]
print(f"   Function ARN: {func_arn}")

# Attach function to CloudFront
dist_resp2 = cf.get_distribution_config(Id=DISTRIBUTION_ID)
etag2 = dist_resp2["ETag"]
config2 = dist_resp2["DistributionConfig"]
dcb = config2["DefaultCacheBehavior"]
fa = dcb.get("FunctionAssociations", {"Quantity": 0, "Items": []})
existing_fns = [f for f in fa.get("Items", []) if "SlashMyCloudBill" not in f.get("FunctionARN", "")]
existing_fns.append({"FunctionARN": func_arn, "EventType": "viewer-request"})
dcb["FunctionAssociations"] = {"Quantity": len(existing_fns), "Items": existing_fns}
config2["DefaultCacheBehavior"] = dcb
cf.update_distribution(Id=DISTRIBUTION_ID, DistributionConfig=config2, IfMatch=etag2)
print("   CloudFront function attached.")

print("\n=== DONE ===")
print(f"Certificate: {cert_arn}")
print(f"DNS: slashmycloudbill.com → {CF_DOMAIN}")
print(f"CloudFront: {DISTRIBUTION_ID} now serves slashmycloudbill.com")
print("\nTest in 5-15 minutes: https://slashmycloudbill.com")
