#!/usr/bin/env python3
"""
Generate PublicSite.drawio - Detailed AWS architecture diagram for SlashMyCloudBill platform.
Uses draw.io XML with AWS4 icon styles, grouped into logical zones with labeled edges.
"""

import xml.etree.ElementTree as ET
from xml.dom import minidom

# ── Helpers ──────────────────────────────────────────────────────────────────

_id_counter = [0]

def _nid():
    _id_counter[0] += 1
    return f"n{_id_counter[0]}"

def _eid():
    _id_counter[0] += 1
    return f"e{_id_counter[0]}"

# AWS4 style prefixes
AWS = "outlineConnect=0;fontColor=#232F3E;gradientColor=none;strokeColor=none;fillColor="
ZONE_STYLE = "rounded=1;whiteSpace=wrap;html=1;dashed=1;dashPattern=5 5;strokeColor=#666666;fillColor=none;fontSize=14;fontStyle=1;verticalAlign=top;align=left;spacingLeft=10;spacingTop=5;"

# AWS icon colors by category
CLR_NETWORK = "#8C4FFF"
CLR_COMPUTE = "#ED7100"
CLR_STORAGE = "#7AA116"
CLR_DATABASE = "#C925D1"
CLR_SECURITY = "#DD344C"
CLR_ML = "#01A88D"
CLR_MGMT = "#E7157B"
CLR_APP = "#E7157B"
CLR_GENERAL = "#232F3E"
CLR_DEVTOOLS = "#C925D1"

# ── Zone definitions (label, x, y, w, h) ────────────────────────────────────

ZONES = {
    "frontend":  ("Frontend / CDN",       20,   20,  620, 340),
    "api":       ("API Layer",            660,   20,  320, 340),
    "compute":   ("Compute (Lambda)",      20,  400,  620, 420),
    "aiml":      ("AI / ML",             660,  400,  320, 200),
    "auth":      ("Authentication",       660,  620,  320, 200),
    "data":      ("Data (DynamoDB)",       20,  860,  960, 280),
    "customer":  ("Customer AWS Account", 1020,  20,  320, 500),
    "cicd":      ("CI/CD",               1020, 560,  320, 260),
}

# ── Component definitions ────────────────────────────────────────────────────
# (zone, label, x_offset, y_offset, style_color, shape_suffix)

def _aws_style(color, shape):
    """Return a draw.io style string for an AWS4 icon."""
    return (
        f"outlineConnect=0;fontColor=#232F3E;gradientColor=none;strokeColor=none;"
        f"fillColor={color};labelBackgroundColor=#ffffff;align=center;fontStyle=1;"
        f"fontSize=10;verticalLabelPosition=bottom;verticalAlign=top;html=1;"
        f"shape=mxgraph.aws4.{shape};"
    )

def _rect_style(color):
    return (
        f"rounded=1;whiteSpace=wrap;html=1;fillColor={color};fontColor=#ffffff;"
        f"fontSize=11;fontStyle=1;strokeColor=none;arcSize=8;"
    )

# ── Build diagram ───────────────────────────────────────────────────────────

def build():
    root = ET.Element("mxGraphModel")
    root.set("dx", "1600")
    root.set("dy", "1200")
    root.set("grid", "1")
    root.set("gridSize", "10")
    root.set("guides", "1")
    root.set("tooltips", "1")
    root.set("connect", "1")
    root.set("arrows", "1")
    root.set("fold", "1")
    root.set("page", "1")
    root.set("pageScale", "1")
    root.set("pageWidth", "1600")
    root.set("pageHeight", "1200")

    rt = ET.SubElement(root, "root")
    ET.SubElement(rt, "mxCell", id="0")
    ET.SubElement(rt, "mxCell", id="1", parent="0")

    ids = {}  # name -> cell id

    # ── Helper to add a cell ────────────────────────────────────────────────
    def add_zone(name, label, x, y, w, h):
        cid = _nid()
        cell = ET.SubElement(rt, "mxCell", id=cid, value=label, style=ZONE_STYLE,
                             vertex="1", parent="1")
        ET.SubElement(cell, "mxGeometry", x=str(x), y=str(y),
                      width=str(w), height=str(h)).set("as", "geometry")
        ids[name] = cid
        return cid

    def add_node(name, label, x, y, w, h, style, parent="1"):
        cid = _nid()
        cell = ET.SubElement(rt, "mxCell", id=cid, value=label, style=style,
                             vertex="1", parent=parent)
        ET.SubElement(cell, "mxGeometry", x=str(x), y=str(y),
                      width=str(w), height=str(h)).set("as", "geometry")
        ids[name] = cid
        return cid

    def add_edge(src, tgt, label="", style=""):
        eid = _eid()
        edge_style = style or (
            "edgeStyle=orthogonalEdgeStyle;rounded=1;orthogonalLoop=1;"
            "jettySize=auto;html=1;strokeColor=#666666;fontSize=9;"
            "fontColor=#333333;exitX=1;exitY=0.5;exitDx=0;exitDy=0;"
        )
        cell = ET.SubElement(rt, "mxCell", id=eid, value=label, style=edge_style,
                             edge="1", parent="1", source=ids[src], target=ids[tgt])
        ET.SubElement(cell, "mxGeometry", relative="1").set("as", "geometry")

    # ── Zones ───────────────────────────────────────────────────────────────
    for zname, (zlabel, zx, zy, zw, zh) in ZONES.items():
        add_zone(zname, zlabel, zx, zy, zw, zh)

    # ── Frontend / CDN zone ─────────────────────────────────────────────────
    add_node("user", "User\n(Browser)",
             40, 60, 60, 60,
             _aws_style(CLR_GENERAL, "user"))

    add_node("r53", "Route 53\nslashmycloudbill.com\neshkolai.com",
             150, 55, 60, 60,
             _aws_style(CLR_NETWORK, "resourceIcon;resIcon=mxgraph.aws4.route_53"))

    add_node("acm", "ACM Certificates\n*.slashmycloudbill.com\n*.eshkolai.com",
             150, 170, 60, 60,
             _aws_style(CLR_SECURITY, "resourceIcon;resIcon=mxgraph.aws4.certificate_manager_3"))

    add_node("cf_smb", "CloudFront\nE2B3GXE4TJTH4Q\n(SMB)",
             290, 55, 60, 60,
             _aws_style(CLR_NETWORK, "resourceIcon;resIcon=mxgraph.aws4.cloudfront"))

    add_node("cf_eshk", "CloudFront\nE12JIHGHK40OLE\n(eshkolai)",
             290, 170, 60, 60,
             _aws_style(CLR_NETWORK, "resourceIcon;resIcon=mxgraph.aws4.cloudfront"))

    add_node("cf_func", "CF Function\nSlashMyCloudBill\n-Router",
             430, 55, 60, 60,
             _aws_style(CLR_NETWORK, "resourceIcon;resIcon=mxgraph.aws4.lambda_function"))

    add_node("s3_site", "S3 Bucket\nslashmycloudbill.com\n(Website)",
             430, 170, 60, 60,
             _aws_style(CLR_STORAGE, "resourceIcon;resIcon=mxgraph.aws4.s3"))

    add_node("s3_storage", "S3 Bucket\naws-bill-analyzer\n-storage\n(Bills/Reports)",
             550, 110, 60, 60,
             _aws_style(CLR_STORAGE, "resourceIcon;resIcon=mxgraph.aws4.s3"))

    # ── API Layer zone ──────────────────────────────────────────────────────
    add_node("apigw", "API Gateway\nHTTP API\nViewMyBill-API\n(25+ routes)",
             720, 80, 78, 78,
             _aws_style(CLR_APP, "resourceIcon;resIcon=mxgraph.aws4.api_gateway"))

    add_node("cors", "CORS Config\nslashmycloudbill.com\neshkolai.com",
             850, 80, 100, 50,
             _rect_style("#555555"))

    # ── Compute zone ────────────────────────────────────────────────────────
    lx = 40
    ly = 450
    lambdas = [
        ("lam_bill",    "Bill Analyzer\nPDF parse → AI → Report",   lx,       ly,      130, 55),
        ("lam_upload",  "Upload Handler\nMultipart → S3 presigned", lx + 160, ly,      130, 55),
        ("lam_otp",     "OTP Handler\n6-digit code, SES, TTL",     lx + 320, ly,      130, 55),
        ("lam_member",  "Member Handler\nAuth, CRUD, AI, Scan",    lx,       ly + 90, 130, 55),
        ("lam_admin",   "Admin Handler\nLeads, Tips, Feedback",    lx + 160, ly + 90, 130, 55),
        ("lam_agent",   "Agent Action\nBedrock Agent group",       lx + 320, ly + 90, 130, 55),
    ]
    for name, label, x, y, w, h in lambdas:
        add_node(name, label, x, y, w, h,
                 _aws_style(CLR_COMPUTE, "resourceIcon;resIcon=mxgraph.aws4.lambda_function"))

    # ── AI/ML zone ──────────────────────────────────────────────────────────
    add_node("bedrock", "Amazon Bedrock\nNova 2 Lite\nus.amazon.nova-2-lite-v1:0\n(Cross-region)",
             700, 440, 78, 78,
             _aws_style(CLR_ML, "resourceIcon;resIcon=mxgraph.aws4.sagemaker"))

    add_node("kb", "Knowledge Base\n30+ Optimization Tips",
             830, 450, 110, 50,
             _rect_style(CLR_ML))

    # ── Auth zone ───────────────────────────────────────────────────────────
    add_node("cognito", "Cognito User Pool\nSlashMyBill-Members\n3-step registration",
             700, 660, 78, 78,
             _aws_style(CLR_SECURITY, "resourceIcon;resIcon=mxgraph.aws4.cognito"))

    add_node("ses", "Amazon SES\nOTP & Notifications\nnoreply@slashmycloudbill.com",
             850, 660, 78, 78,
             _aws_style(CLR_APP, "resourceIcon;resIcon=mxgraph.aws4.simple_email_service"))

    # ── Data zone ───────────────────────────────────────────────────────────
    tables = [
        ("ddb_leads",    "ViewMyBill\n-Leads",                30,  900, 100, 50),
        ("ddb_otp",      "ViewMyBill\n-OTP\n(TTL 5min)",     150, 900, 100, 50),
        ("ddb_tips",     "ViewMyBill\n-CostOptimization\nTips", 270, 900, 110, 50),
        ("ddb_members",  "MemberPortal\n-Members",            400, 900, 100, 50),
        ("ddb_accounts", "MemberPortal\n-Accounts",           520, 900, 100, 50),
        ("ddb_feedback", "MemberPortal\n-AgentFeedback",      640, 900, 110, 50),
        ("ddb_metrics",  "MemberPortal\n-BusinessMetrics",    770, 900, 110, 50),
        ("ddb_spot",     "SpotSavings\nLedger\n(Gainshare)",  900, 900, 100, 50),
    ]
    for name, label, x, y, w, h in tables:
        add_node(name, label, x, y, w, h,
                 _aws_style(CLR_DATABASE, "resourceIcon;resIcon=mxgraph.aws4.dynamodb"))

    # ── Customer Account zone ───────────────────────────────────────────────
    add_node("sts", "STS AssumeRole\nSlashMyBill-{ID}\n(Cross-account)",
             1060, 60, 78, 78,
             _aws_style(CLR_SECURITY, "resourceIcon;resIcon=mxgraph.aws4.role"))

    add_node("cust_ce", "Cost Explorer\nGetCostAndUsage",
             1060, 180, 78, 60,
             _aws_style(CLR_MGMT, "resourceIcon;resIcon=mxgraph.aws4.cost_explorer"))

    add_node("cust_ec2", "EC2",  1060, 280, 50, 50,
             _aws_style(CLR_COMPUTE, "resourceIcon;resIcon=mxgraph.aws4.ec2"))
    add_node("cust_rds", "RDS",  1130, 280, 50, 50,
             _aws_style(CLR_DATABASE, "resourceIcon;resIcon=mxgraph.aws4.rds"))
    add_node("cust_s3",  "S3",   1200, 280, 50, 50,
             _aws_style(CLR_STORAGE, "resourceIcon;resIcon=mxgraph.aws4.s3"))
    add_node("cust_ebs", "EBS",  1060, 360, 50, 50,
             _aws_style(CLR_STORAGE, "resourceIcon;resIcon=mxgraph.aws4.elastic_block_store"))
    add_node("cust_elb", "ELB",  1130, 360, 50, 50,
             _aws_style(CLR_NETWORK, "resourceIcon;resIcon=mxgraph.aws4.elastic_load_balancing"))
    add_node("cust_snap","Snapshots", 1200, 360, 50, 50,
             _aws_style(CLR_STORAGE, "resourceIcon;resIcon=mxgraph.aws4.snapshot"))

    # ── CI/CD zone ──────────────────────────────────────────────────────────
    add_node("github", "GitHub Actions\nCI/CD Pipeline\nOIDC Auth",
             1060, 600, 78, 78,
             _aws_style(CLR_DEVTOOLS, "resourceIcon;resIcon=mxgraph.aws4.codecommit"))

    add_node("oidc", "IAM OIDC Role\ngithub-oidc-role\n(No stored secrets)",
             1180, 600, 120, 60,
             _aws_style(CLR_SECURITY, "resourceIcon;resIcon=mxgraph.aws4.role"))

    add_node("pipeline", "Package → Deploy Stack\n→ Update Lambdas\n→ Deploy Frontend\n→ Invalidate Cache",
             1060, 720, 240, 60,
             _rect_style("#555555"))

    # ── Spot Management zone ────────────────────────────────────────────────
    add_node("sns_spot", "SNS Topic\nSlashMyBill\n-SpotInterruptions",
             700, 550, 78, 60,
             _aws_style(CLR_APP, "resourceIcon;resIcon=mxgraph.aws4.sns"))

    add_node("cust_eb", "EventBridge Rule\nSpot Interruption\nMonitor",
             1200, 440, 78, 60,
             _aws_style(CLR_APP, "resourceIcon;resIcon=mxgraph.aws4.eventbridge"))

    add_node("cust_asg", "Auto Scaling\nGroups\n(Spot Migration)",
             1270, 280, 60, 50,
             _aws_style(CLR_COMPUTE, "resourceIcon;resIcon=mxgraph.aws4.auto_scaling2"))

    add_node("sched_exec", "Scheduler\nExecutor Lambda\n(Stop/Start)",
             lx + 480, ly + 90, 130, 55,
             _aws_style(CLR_COMPUTE, "resourceIcon;resIcon=mxgraph.aws4.lambda_function"))

    add_node("eb_sched", "EventBridge\nScheduler\n(Cron jobs)",
             lx + 480, ly, 130, 55,
             _aws_style(CLR_APP, "resourceIcon;resIcon=mxgraph.aws4.eventbridge"))

    # ── Edges ───────────────────────────────────────────────────────────────
    edge_style_base = (
        "edgeStyle=orthogonalEdgeStyle;rounded=1;orthogonalLoop=1;"
        "jettySize=auto;html=1;fontSize=9;fontColor=#333333;"
    )
    es_blue   = edge_style_base + "strokeColor=#4A90D9;"
    es_green  = edge_style_base + "strokeColor=#7AA116;"
    es_orange = edge_style_base + "strokeColor=#ED7100;"
    es_purple = edge_style_base + "strokeColor=#8C4FFF;"
    es_red    = edge_style_base + "strokeColor=#DD344C;"
    es_gray   = edge_style_base + "strokeColor=#666666;"

    # User → Route53 → CloudFront
    add_edge("user",    "r53",      "DNS lookup",       es_blue)
    add_edge("r53",     "cf_smb",   "A/AAAA alias",     es_blue)
    add_edge("r53",     "cf_eshk",  "A/AAAA alias",     es_blue)
    add_edge("acm",     "cf_smb",   "TLS cert",         es_red)
    add_edge("acm",     "cf_eshk",  "TLS cert",         es_red)

    # CloudFront → CF Function → S3
    add_edge("cf_smb",  "cf_func",  "Request routing",  es_blue)
    add_edge("cf_func", "s3_site",  "Static assets",    es_green)
    add_edge("cf_eshk", "s3_site",  "Origin",           es_green)

    # CloudFront → API Gateway
    add_edge("cf_smb",  "apigw",    "/api/* proxy",     es_orange)

    # API Gateway → Lambdas
    add_edge("apigw", "lam_bill",   "/analyze",         es_orange)
    add_edge("apigw", "lam_upload", "/upload",           es_orange)
    add_edge("apigw", "lam_otp",    "/otp/*",            es_orange)
    add_edge("apigw", "lam_member", "/members/*",        es_orange)
    add_edge("apigw", "lam_admin",  "/admin/*",          es_orange)

    # Lambda → S3 storage
    add_edge("lam_bill",   "s3_storage", "Read bill / Write report", es_green)
    add_edge("lam_upload", "s3_storage", "Presigned URL",            es_green)

    # Lambda → Bedrock
    add_edge("lam_bill",   "bedrock", "AI analysis",     es_purple)
    add_edge("lam_member", "bedrock", "AI query",        es_purple)
    add_edge("lam_agent",  "bedrock", "Agent actions",   es_purple)
    add_edge("bedrock",    "kb",      "Tips lookup",     es_purple)

    # Lambda → Auth
    add_edge("lam_otp",    "ses",     "Send OTP email",  es_red)
    add_edge("lam_member", "cognito", "Auth / Register", es_red)
    add_edge("lam_member", "ses",     "Notifications",   es_red)

    # Lambda → DynamoDB
    add_edge("lam_bill",   "ddb_leads",    "Save lead",       es_gray)
    add_edge("lam_otp",    "ddb_otp",      "Store/verify OTP",es_gray)
    add_edge("lam_admin",  "ddb_tips",     "CRUD tips",       es_gray)
    add_edge("lam_member", "ddb_members",  "Member data",     es_gray)
    add_edge("lam_member", "ddb_accounts", "Account CRUD",    es_gray)
    add_edge("lam_member", "ddb_feedback", "AI feedback",     es_gray)
    add_edge("lam_member", "ddb_metrics",  "Business metrics",es_gray)
    add_edge("lam_admin",  "ddb_leads",    "Manage leads",    es_gray)
    add_edge("lam_admin",  "ddb_feedback", "View feedback",   es_gray)

    # Lambda → Customer Account
    add_edge("lam_member", "sts",     "AssumeRole",      es_red)
    add_edge("sts",        "cust_ce", "Cost data",       es_orange)
    add_edge("sts",        "cust_ec2","Describe/Stop",   es_orange)
    add_edge("sts",        "cust_rds","Describe/Stop",   es_orange)
    add_edge("sts",        "cust_s3", "Lifecycle rules", es_orange)

    # CI/CD
    add_edge("github", "oidc",     "OIDC auth",         es_red)
    add_edge("github", "s3_site",  "Deploy frontend",   es_green)
    add_edge("github", "lam_bill", "Update Lambdas",    es_orange)
    add_edge("github", "cf_smb",   "Invalidate cache",  es_blue)

    # Spot Management
    add_edge("lam_member", "sns_spot",   "Interruption emails", es_purple)
    add_edge("cust_eb",    "sns_spot",   "Push interruption events", es_red)
    add_edge("lam_member", "ddb_spot",   "Savings ledger",     es_gray)
    add_edge("sts",        "cust_asg",   "Migrate to Spot",    es_orange)
    add_edge("sts",        "cust_eb",    "Deploy rule",        es_red)

    # Scheduler
    add_edge("eb_sched",   "sched_exec", "Trigger",            es_orange)
    add_edge("sched_exec", "sts",        "Cross-account",      es_red)

    return root


def main():
    root = build()
    rough = ET.tostring(root, encoding="unicode")
    pretty = minidom.parseString(rough).toprettyxml(indent="  ")
    # Remove XML declaration line
    lines = pretty.split("\n")
    if lines[0].startswith("<?xml"):
        lines = lines[1:]
    content = "\n".join(lines)

    with open("PublicSite.drawio", "w", encoding="utf-8") as f:
        f.write(content)
    print("✅ PublicSite.drawio generated successfully!")
    print("   Open in draw.io / diagrams.net to view the architecture diagram.")


if __name__ == "__main__":
    main()
