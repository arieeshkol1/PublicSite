#!/usr/bin/env python3
"""
Made4Net Access Patterns Diagram Generator
Creates a complete draw.io diagram showing 3 user access patterns
"""

def create_drawio_header():
    return '''<mxfile host="app.diagrams.net" modified="2026-02-11T12:00:00.000Z" agent="Python" version="24.0.0" type="device">
  <diagram name="Access-Patterns" id="access-patterns">
    <mxGraphModel dx="1422" dy="794" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="1" pageScale="1" pageWidth="1920" pageHeight="1080" math="0" shadow="0">
      <root>
        <mxCell id="0"/>
        <mxCell id="1" parent="0"/>
'''

def create_title():
    return '''        <!-- Title -->
        <mxCell id="title" value="Made4Net Access Patterns &amp; User Flows" style="text;html=1;strokeColor=none;fillColor=none;align=center;verticalAlign=middle;whiteSpace=wrap;rounded=0;fontSize=32;fontStyle=1" vertex="1" parent="1">
          <mxGeometry x="560" y="20" width="800" height="50" as="geometry"/>
        </mxCell>
        <mxCell id="subtitle" value="End User | IoT Device | Hosting Engineer" style="text;html=1;strokeColor=none;fillColor=none;align=center;verticalAlign=middle;whiteSpace=wrap;rounded=0;fontSize=18;fontColor=#666666" vertex="1" parent="1">
          <mxGeometry x="660" y="70" width="600" height="30" as="geometry"/>
        </mxCell>
'''

def create_section_headers():
    return '''        <!-- Section Headers -->
        <mxCell id="header1" value="END USER ACCESS" style="rounded=1;whiteSpace=wrap;html=1;fontSize=16;fontStyle=1;fillColor=#0066CC;fontColor=#FFFFFF;strokeColor=#004080" vertex="1" parent="1">
          <mxGeometry x="80" y="120" width="520" height="40" as="geometry"/>
        </mxCell>
        <mxCell id="header2" value="IoT DEVICE ACCESS" style="rounded=1;whiteSpace=wrap;html=1;fontSize=16;fontStyle=1;fillColor=#00AA00;fontColor=#FFFFFF;strokeColor=#007700" vertex="1" parent="1">
          <mxGeometry x="700" y="120" width="520" height="40" as="geometry"/>
        </mxCell>
        <mxCell id="header3" value="HOSTING ENGINEER ACCESS" style="rounded=1;whiteSpace=wrap;html=1;fontSize=16;fontStyle=1;fillColor=#FF6600;fontColor=#FFFFFF;strokeColor=#CC5200" vertex="1" parent="1">
          <mxGeometry x="1320" y="120" width="520" height="40" as="geometry"/>
        </mxCell>
'''

# Continue in next part...

def create_end_user_flow():
    return '''        <!-- END USER FLOW -->
        <!-- User Icon -->
        <mxCell id="user1" value="Warehouse&#xa;Manager" style="shape=actor;whiteSpace=wrap;html=1;fillColor=#0066CC;fontColor=#FFFFFF;strokeColor=#004080" vertex="1" parent="1">
          <mxGeometry x="280" y="200" width="60" height="80" as="geometry"/>
        </mxCell>
        
        <!-- CloudFront -->
        <mxCell id="cloudfront" value="Amazon&#xa;CloudFront" style="sketch=0;points=[[0,0,0],[0.25,0,0],[0.5,0,0],[0.75,0,0],[1,0,0],[0,1,0],[0.25,1,0],[0.5,1,0],[0.75,1,0],[1,1,0],[0,0.25,0],[0,0.5,0],[0,0.75,0],[1,0.25,0],[1,0.5,0],[1,0.75,0]];outlineConnect=0;fontColor=#232F3E;fillColor=#FF9900;strokeColor=#ffffff;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=12;fontStyle=0;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.cloudfront;" vertex="1" parent="1">
          <mxGeometry x="271" y="320" width="78" height="78" as="geometry"/>
        </mxCell>
        
        <!-- ALB -->
        <mxCell id="alb" value="Application&#xa;Load Balancer" style="sketch=0;points=[[0,0,0],[0.25,0,0],[0.5,0,0],[0.75,0,0],[1,0,0],[0,1,0],[0.25,1,0],[0.5,1,0],[0.75,1,0],[1,1,0],[0,0.25,0],[0,0.5,0],[0,0.75,0],[1,0.25,0],[1,0.5,0],[1,0.75,0]];outlineConnect=0;fontColor=#232F3E;fillColor=#8C4FFF;strokeColor=#ffffff;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=12;fontStyle=0;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.elastic_load_balancing;" vertex="1" parent="1">
          <mxGeometry x="271" y="440" width="78" height="78" as="geometry"/>
        </mxCell>
        
        <!-- EC2 -->
        <mxCell id="ec2-user" value="EC2 Auto&#xa;Scaling Group" style="sketch=0;points=[[0,0,0],[0.25,0,0],[0.5,0,0],[0.75,0,0],[1,0,0],[0,1,0],[0.25,1,0],[0.5,1,0],[0.75,1,0],[1,1,0],[0,0.25,0],[0,0.5,0],[0,0.75,0],[1,0.25,0],[1,0.5,0],[1,0.75,0]];outlineConnect=0;fontColor=#232F3E;fillColor=#ED7100;strokeColor=#ffffff;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=12;fontStyle=0;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.auto_scaling2;" vertex="1" parent="1">
          <mxGeometry x="271" y="560" width="78" height="78" as="geometry"/>
        </mxCell>
        
        <!-- Cognito -->
        <mxCell id="cognito" value="Amazon&#xa;Cognito" style="sketch=0;points=[[0,0,0],[0.25,0,0],[0.5,0,0],[0.75,0,0],[1,0,0],[0,1,0],[0.25,1,0],[0.5,1,0],[0.75,1,0],[1,1,0],[0,0.25,0],[0,0.5,0],[0,0.75,0],[1,0.25,0],[1,0.5,0],[1,0.75,0]];outlineConnect=0;fontColor=#232F3E;fillColor=#DD344C;strokeColor=#ffffff;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=12;fontStyle=0;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.cognito;" vertex="1" parent="1">
          <mxGeometry x="171" y="680" width="78" height="78" as="geometry"/>
        </mxCell>
        
        <!-- RDS -->
        <mxCell id="rds" value="Amazon&#xa;RDS" style="sketch=0;points=[[0,0,0],[0.25,0,0],[0.5,0,0],[0.75,0,0],[1,0,0],[0,1,0],[0.25,1,0],[0.5,1,0],[0.75,1,0],[1,1,0],[0,0.25,0],[0,0.5,0],[0,0.75,0],[1,0.25,0],[1,0.5,0],[1,0.75,0]];outlineConnect=0;fontColor=#232F3E;fillColor=#C925D1;strokeColor=#ffffff;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=12;fontStyle=0;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.rds;" vertex="1" parent="1">
          <mxGeometry x="371" y="680" width="78" height="78" as="geometry"/>
        </mxCell>
        
        <!-- Arrows for End User -->
        <mxCell id="arrow1-1" value="① HTTPS (443)" style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;strokeColor=#0066CC;strokeWidth=3;fontSize=12;fontColor=#0066CC" edge="1" parent="1" source="user1" target="cloudfront">
          <mxGeometry relative="1" as="geometry"/>
        </mxCell>
        <mxCell id="arrow1-2" value="② Origin Request" style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;strokeColor=#0066CC;strokeWidth=3;fontSize=12;fontColor=#0066CC" edge="1" parent="1" source="cloudfront" target="alb">
          <mxGeometry relative="1" as="geometry"/>
        </mxCell>
        <mxCell id="arrow1-3" value="③ Load Balanced" style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;strokeColor=#0066CC;strokeWidth=3;fontSize=12;fontColor=#0066CC" edge="1" parent="1" source="alb" target="ec2-user">
          <mxGeometry relative="1" as="geometry"/>
        </mxCell>
        <mxCell id="arrow1-4" value="④ Auth" style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;strokeColor=#0066CC;strokeWidth=2;fontSize=12;fontColor=#0066CC" edge="1" parent="1" source="ec2-user" target="cognito">
          <mxGeometry relative="1" as="geometry"/>
        </mxCell>
        <mxCell id="arrow1-5" value="⑤ Data Query" style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;strokeColor=#0066CC;strokeWidth=2;fontSize=12;fontColor=#0066CC" edge="1" parent="1" source="ec2-user" target="rds">
          <mxGeometry relative="1" as="geometry"/>
        </mxCell>
        
        <!-- End User Info Box -->
        <mxCell id="info1" value="&lt;b&gt;END USER ACCESS&lt;/b&gt;&lt;br&gt;• Protocol: HTTPS (443)&lt;br&gt;• Auth: Cognito SSO + MFA&lt;br&gt;• Latency: &amp;lt;200ms&lt;br&gt;• Entry: CloudFront → ALB&lt;br&gt;• Security: WAF + DDoS&lt;br&gt;• Pattern: Request/Response" style="rounded=1;whiteSpace=wrap;html=1;align=left;verticalAlign=top;fillColor=#E6F2FF;strokeColor=#0066CC;fontSize=11" vertex="1" parent="1">
          <mxGeometry x="80" y="800" width="520" height="120" as="geometry"/>
        </mxCell>
'''

def create_iot_flow():
    return '''        <!-- IoT DEVICE FLOW -->
        <!-- IoT Devices -->
        <mxCell id="robot" value="Robot" style="shape=image;html=1;verticalAlign=top;verticalLabelPosition=bottom;labelBackgroundColor=#ffffff;imageAspect=0;aspect=fixed;image=https://cdn-icons-png.flaticon.com/512/4712/4712109.png;fillColor=#00AA00" vertex="1" parent="1">
          <mxGeometry x="820" y="200" width="60" height="60" as="geometry"/>
        </mxCell>
        <mxCell id="sensor" value="Sensor" style="shape=image;html=1;verticalAlign=top;verticalLabelPosition=bottom;labelBackgroundColor=#ffffff;imageAspect=0;aspect=fixed;image=https://cdn-icons-png.flaticon.com/512/2920/2920277.png;fillColor=#00AA00" vertex="1" parent="1">
          <mxGeometry x="920" y="200" width="60" height="60" as="geometry"/>
        </mxCell>
        <mxCell id="shelf" value="Smart Shelf" style="shape=image;html=1;verticalAlign=top;verticalLabelPosition=bottom;labelBackgroundColor=#ffffff;imageAspect=0;aspect=fixed;image=https://cdn-icons-png.flaticon.com/512/2920/2920231.png;fillColor=#00AA00" vertex="1" parent="1">
          <mxGeometry x="1020" y="200" width="60" height="60" as="geometry"/>
        </mxCell>
        <mxCell id="scanner" value="Scanner" style="shape=image;html=1;verticalAlign=top;verticalLabelPosition=bottom;labelBackgroundColor=#ffffff;imageAspect=0;aspect=fixed;image=https://cdn-icons-png.flaticon.com/512/2920/2920235.png;fillColor=#00AA00" vertex="1" parent="1">
          <mxGeometry x="1120" y="200" width="60" height="60" as="geometry"/>
        </mxCell>
        
        <!-- IoT Core -->
        <mxCell id="iotcore" value="AWS&#xa;IoT Core" style="sketch=0;points=[[0,0,0],[0.25,0,0],[0.5,0,0],[0.75,0,0],[1,0,0],[0,1,0],[0.25,1,0],[0.5,1,0],[0.75,1,0],[1,1,0],[0,0.25,0],[0,0.5,0],[0,0.75,0],[1,0.25,0],[1,0.5,0],[1,0.75,0]];outlineConnect=0;fontColor=#232F3E;fillColor=#7AA116;strokeColor=#ffffff;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=12;fontStyle=0;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.iot_core;" vertex="1" parent="1">
          <mxGeometry x="921" y="320" width="78" height="78" as="geometry"/>
        </mxCell>
        
        <!-- IoT Rules Engine -->
        <mxCell id="rules" value="IoT Rules&#xa;Engine" style="sketch=0;points=[[0,0,0],[0.25,0,0],[0.5,0,0],[0.75,0,0],[1,0,0],[0,1,0],[0.25,1,0],[0.5,1,0],[0.75,1,0],[1,1,0],[0,0.25,0],[0,0.5,0],[0,0.75,0],[1,0.25,0],[1,0.5,0],[1,0.75,0]];outlineConnect=0;fontColor=#232F3E;fillColor=#7AA116;strokeColor=#ffffff;dashed=0;verticalAlign=top;align=center;html=1;fontSize=12;fontStyle=0;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.iot_rule;" vertex="1" parent="1">
          <mxGeometry x="921" y="440" width="78" height="78" as="geometry"/>
        </mxCell>
        
        <!-- Kinesis Stream -->
        <mxCell id="kinesis" value="Kinesis&#xa;Streams" style="sketch=0;points=[[0,0,0],[0.25,0,0],[0.5,0,0],[0.75,0,0],[1,0,0],[0,1,0],[0.25,1,0],[0.5,1,0],[0.75,1,0],[1,1,0],[0,0.25,0],[0,0.5,0],[0,0.75,0],[1,0.25,0],[1,0.5,0],[1,0.75,0]];outlineConnect=0;fontColor=#232F3E;fillColor=#8C4FFF;strokeColor=#ffffff;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=12;fontStyle=0;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.kinesis_data_streams;" vertex="1" parent="1">
          <mxGeometry x="721" y="560" width="58" height="58" as="geometry"/>
        </mxCell>
        
        <!-- Lambda -->
        <mxCell id="lambda-iot" value="Lambda" style="sketch=0;points=[[0,0,0],[0.25,0,0],[0.5,0,0],[0.75,0,0],[1,0,0],[0,1,0],[0.25,1,0],[0.5,1,0],[0.75,1,0],[1,1,0],[0,0.25,0],[0,0.5,0],[0,0.75,0],[1,0.25,0],[1,0.5,0],[1,0.75,0]];outlineConnect=0;fontColor=#232F3E;fillColor=#ED7100;strokeColor=#ffffff;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=12;fontStyle=0;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.lambda;" vertex="1" parent="1">
          <mxGeometry x="721" y="650" width="58" height="58" as="geometry"/>
        </mxCell>
        
        <!-- DynamoDB -->
        <mxCell id="dynamodb" value="DynamoDB" style="sketch=0;points=[[0,0,0],[0.25,0,0],[0.5,0,0],[0.75,0,0],[1,0,0],[0,1,0],[0.25,1,0],[0.5,1,0],[0.75,1,0],[1,1,0],[0,0.25,0],[0,0.5,0],[0,0.75,0],[1,0.25,0],[1,0.5,0],[1,0.75,0]];outlineConnect=0;fontColor=#232F3E;fillColor=#C925D1;strokeColor=#ffffff;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=12;fontStyle=0;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.dynamodb;" vertex="1" parent="1">
          <mxGeometry x="721" y="740" width="58" height="58" as="geometry"/>
        </mxCell>
        
        <!-- Firehose -->
        <mxCell id="firehose" value="Firehose" style="sketch=0;points=[[0,0,0],[0.25,0,0],[0.5,0,0],[0.75,0,0],[1,0,0],[0,1,0],[0.25,1,0],[0.5,1,0],[0.75,1,0],[1,1,0],[0,0.25,0],[0,0.5,0],[0,0.75,0],[1,0.25,0],[1,0.5,0],[1,0.75,0]];outlineConnect=0;fontColor=#232F3E;fillColor=#8C4FFF;strokeColor=#ffffff;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=12;fontStyle=0;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.kinesis_data_firehose;" vertex="1" parent="1">
          <mxGeometry x="931" y="650" width="58" height="58" as="geometry"/>
        </mxCell>
        
        <!-- S3 -->
        <mxCell id="s3" value="S3" style="sketch=0;points=[[0,0,0],[0.25,0,0],[0.5,0,0],[0.75,0,0],[1,0,0],[0,1,0],[0.25,1,0],[0.5,1,0],[0.75,1,0],[1,1,0],[0,0.25,0],[0,0.5,0],[0,0.75,0],[1,0.25,0],[1,0.5,0],[1,0.75,0]];outlineConnect=0;fontColor=#232F3E;fillColor=#7AA116;strokeColor=#ffffff;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=12;fontStyle=0;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.s3;" vertex="1" parent="1">
          <mxGeometry x="931" y="740" width="58" height="58" as="geometry"/>
        </mxCell>
        
        <!-- IoT Events -->
        <mxCell id="iotevents" value="IoT Events" style="sketch=0;points=[[0,0,0],[0.25,0,0],[0.5,0,0],[0.75,0,0],[1,0,0],[0,1,0],[0.25,1,0],[0.5,1,0],[0.75,1,0],[1,1,0],[0,0.25,0],[0,0.5,0],[0,0.75,0],[1,0.25,0],[1,0.5,0],[1,0.75,0]];outlineConnect=0;fontColor=#232F3E;fillColor=#E7157B;strokeColor=#ffffff;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=12;fontStyle=0;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.iot_events;" vertex="1" parent="1">
          <mxGeometry x="1091" y="650" width="58" height="58" as="geometry"/>
        </mxCell>
        
        <!-- SNS -->
        <mxCell id="sns" value="SNS" style="sketch=0;points=[[0,0,0],[0.25,0,0],[0.5,0,0],[0.75,0,0],[1,0,0],[0,1,0],[0.25,1,0],[0.5,1,0],[0.75,1,0],[1,1,0],[0,0.25,0],[0,0.5,0],[0,0.75,0],[1,0.25,0],[1,0.5,0],[1,0.75,0]];outlineConnect=0;fontColor=#232F3E;fillColor=#E7157B;strokeColor=#ffffff;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=12;fontStyle=0;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.sns;" vertex="1" parent="1">
          <mxGeometry x="1091" y="740" width="58" height="58" as="geometry"/>
        </mxCell>
        
        <!-- Arrows for IoT -->
        <mxCell id="arrow2-1" value="① MQTT/TLS (8883)" style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;strokeColor=#00AA00;strokeWidth=3;fontSize=12;fontColor=#00AA00;entryX=0.5;entryY=0;entryDx=0;entryDy=0;entryPerimeter=0" edge="1" parent="1" target="iotcore">
          <mxGeometry relative="1" as="geometry">
            <mxPoint x="960" y="270" as="sourcePoint"/>
          </mxGeometry>
        </mxCell>
        <mxCell id="arrow2-2" value="② Rules Engine" style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;strokeColor=#00AA00;strokeWidth=3;fontSize=12;fontColor=#00AA00" edge="1" parent="1" source="iotcore" target="rules">
          <mxGeometry relative="1" as="geometry"/>
        </mxCell>
        <mxCell id="arrow2-3" value="Real-Time" style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;strokeColor=#00AA00;strokeWidth=2;fontSize=11;fontColor=#00AA00" edge="1" parent="1" source="rules" target="kinesis">
          <mxGeometry relative="1" as="geometry"/>
        </mxCell>
        <mxCell id="arrow2-4" value="" style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;strokeColor=#00AA00;strokeWidth=2" edge="1" parent="1" source="kinesis" target="lambda-iot">
          <mxGeometry relative="1" as="geometry"/>
        </mxCell>
        <mxCell id="arrow2-5" value="" style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;strokeColor=#00AA00;strokeWidth=2" edge="1" parent="1" source="lambda-iot" target="dynamodb">
          <mxGeometry relative="1" as="geometry"/>
        </mxCell>
        <mxCell id="arrow2-6" value="Analytics" style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;strokeColor=#00AA00;strokeWidth=2;fontSize=11;fontColor=#00AA00" edge="1" parent="1" source="rules" target="firehose">
          <mxGeometry relative="1" as="geometry"/>
        </mxCell>
        <mxCell id="arrow2-7" value="" style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;strokeColor=#00AA00;strokeWidth=2" edge="1" parent="1" source="firehose" target="s3">
          <mxGeometry relative="1" as="geometry"/>
        </mxCell>
        <mxCell id="arrow2-8" value="Alerts" style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;strokeColor=#00AA00;strokeWidth=2;fontSize=11;fontColor=#00AA00" edge="1" parent="1" source="rules" target="iotevents">
          <mxGeometry relative="1" as="geometry"/>
        </mxCell>
        <mxCell id="arrow2-9" value="" style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;strokeColor=#00AA00;strokeWidth=2" edge="1" parent="1" source="iotevents" target="sns">
          <mxGeometry relative="1" as="geometry"/>
        </mxCell>
        
        <!-- IoT Info Box -->
        <mxCell id="info2" value="&lt;b&gt;IoT DEVICE ACCESS&lt;/b&gt;&lt;br&gt;• Protocol: MQTT/TLS (8883)&lt;br&gt;• Auth: X.509 Certificates&lt;br&gt;• Latency: &amp;lt;50ms&lt;br&gt;• Entry: IoT Core → Rules&lt;br&gt;• Devices: Robot, Sensor, Shelf&lt;br&gt;• Pattern: Persistent Connection" style="rounded=1;whiteSpace=wrap;html=1;align=left;verticalAlign=top;fillColor=#E6FFE6;strokeColor=#00AA00;fontSize=11" vertex="1" parent="1">
          <mxGeometry x="700" y="820" width="520" height="100" as="geometry"/>
        </mxCell>
'''

def create_engineer_flow():
    return '''        <!-- HOSTING ENGINEER FLOW -->
        <!-- Engineer Icon -->
        <mxCell id="engineer" value="Hosting&#xa;Engineer" style="shape=actor;whiteSpace=wrap;html=1;fillColor=#FF6600;fontColor=#FFFFFF;strokeColor=#CC5200" vertex="1" parent="1">
          <mxGeometry x="1530" y="200" width="60" height="80" as="geometry"/>
        </mxCell>
        
        <!-- AWS Console -->
        <mxCell id="console" value="AWS&#xa;Console" style="sketch=0;points=[[0,0,0],[0.25,0,0],[0.5,0,0],[0.75,0,0],[1,0,0],[0,1,0],[0.25,1,0],[0.5,1,0],[0.75,1,0],[1,1,0],[0,0.25,0],[0,0.5,0],[0,0.75,0],[1,0.25,0],[1,0.5,0],[1,0.75,0]];outlineConnect=0;fontColor=#232F3E;fillColor=#DD344C;strokeColor=#ffffff;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=12;fontStyle=0;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.management_console;" vertex="1" parent="1">
          <mxGeometry x="1521" y="320" width="78" height="78" as="geometry"/>
        </mxCell>
        
        <!-- Systems Manager -->
        <mxCell id="ssm" value="Systems&#xa;Manager" style="sketch=0;points=[[0,0,0],[0.25,0,0],[0.5,0,0],[0.75,0,0],[1,0,0],[0,1,0],[0.25,1,0],[0.5,1,0],[0.75,1,0],[1,1,0],[0,0.25,0],[0,0.5,0],[0,0.75,0],[1,0.25,0],[1,0.5,0],[1,0.75,0]];outlineConnect=0;fontColor=#232F3E;fillColor=#E7157B;strokeColor=#ffffff;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=12;fontStyle=0;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.systems_manager;" vertex="1" parent="1">
          <mxGeometry x="1521" y="440" width="78" height="78" as="geometry"/>
        </mxCell>
        
        <!-- Fleet Manager -->
        <mxCell id="fleet" value="Fleet&#xa;Manager" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#FFE6CC;strokeColor=#FF6600;fontSize=11" vertex="1" parent="1">
          <mxGeometry x="1360" y="560" width="80" height="60" as="geometry"/>
        </mxCell>
        
        <!-- Session Manager -->
        <mxCell id="session" value="Session&#xa;Manager" style="rounded=1;whiteSpace=wrap;html=1;fillColor=#FFE6CC;strokeColor=#FF6600;fontSize=11" vertex="1" parent="1">
          <mxGeometry x="1460" y="560" width="80" height="60" as="geometry"/>
        </mxCell>
        
        <!-- CloudWatch -->
        <mxCell id="cloudwatch" value="CloudWatch" style="sketch=0;points=[[0,0,0],[0.25,0,0],[0.5,0,0],[0.75,0,0],[1,0,0],[0,1,0],[0.25,1,0],[0.5,1,0],[0.75,1,0],[1,1,0],[0,0.25,0],[0,0.5,0],[0,0.75,0],[1,0.25,0],[1,0.5,0],[1,0.75,0]];outlineConnect=0;fontColor=#232F3E;fillColor=#E7157B;strokeColor=#ffffff;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=12;fontStyle=0;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.cloudwatch_2;" vertex="1" parent="1">
          <mxGeometry x="1561" y="560" width="58" height="58" as="geometry"/>
        </mxCell>
        
        <!-- X-Ray -->
        <mxCell id="xray" value="X-Ray" style="sketch=0;points=[[0,0,0],[0.25,0,0],[0.5,0,0],[0.75,0,0],[1,0,0],[0,1,0],[0.25,1,0],[0.5,1,0],[0.75,1,0],[1,1,0],[0,0.25,0],[0,0.5,0],[0,0.75,0],[1,0.25,0],[1,0.5,0],[1,0.75,0]];outlineConnect=0;fontColor=#232F3E;fillColor=#E7157B;strokeColor=#ffffff;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=12;fontStyle=0;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.x_ray;" vertex="1" parent="1">
          <mxGeometry x="1661" y="560" width="58" height="58" as="geometry"/>
        </mxCell>
        
        <!-- Target EC2 -->
        <mxCell id="ec2-target" value="EC2&#xa;Instance" style="sketch=0;points=[[0,0,0],[0.25,0,0],[0.5,0,0],[0.75,0,0],[1,0,0],[0,1,0],[0.25,1,0],[0.5,1,0],[0.75,1,0],[1,1,0],[0,0.25,0],[0,0.5,0],[0,0.75,0],[1,0.25,0],[1,0.5,0],[1,0.75,0]];outlineConnect=0;fontColor=#232F3E;fillColor=#ED7100;strokeColor=#ffffff;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=12;fontStyle=0;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.ec2;" vertex="1" parent="1">
          <mxGeometry x="1471" y="680" width="58" height="58" as="geometry"/>
        </mxCell>
        
        <!-- Arrows for Engineer -->
        <mxCell id="arrow3-1" value="① IAM + MFA" style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;strokeColor=#FF6600;strokeWidth=3;fontSize=12;fontColor=#FF6600" edge="1" parent="1" source="engineer" target="console">
          <mxGeometry relative="1" as="geometry"/>
        </mxCell>
        <mxCell id="arrow3-2" value="② Navigate" style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;strokeColor=#FF6600;strokeWidth=3;fontSize=12;fontColor=#FF6600" edge="1" parent="1" source="console" target="ssm">
          <mxGeometry relative="1" as="geometry"/>
        </mxCell>
        <mxCell id="arrow3-3" value="③ Tools" style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;strokeColor=#FF6600;strokeWidth=2;fontSize=11;fontColor=#FF6600;exitX=0.5;exitY=1;exitDx=0;exitDy=0;exitPerimeter=0" edge="1" parent="1" source="ssm">
          <mxGeometry relative="1" as="geometry">
            <mxPoint x="1560" y="560" as="targetPoint"/>
          </mxGeometry>
        </mxCell>
        <mxCell id="arrow3-4" value="Shell Access" style="edgeStyle=orthogonalEdgeStyle;rounded=0;orthogonalLoop=1;jettySize=auto;html=1;strokeColor=#FF6600;strokeWidth=2;fontSize=11;fontColor=#FF6600" edge="1" parent="1" source="session" target="ec2-target">
          <mxGeometry relative="1" as="geometry"/>
        </mxCell>
        
        <!-- Engineer Info Box -->
        <mxCell id="info3" value="&lt;b&gt;HOSTING ENGINEER ACCESS&lt;/b&gt;&lt;br&gt;• Protocol: HTTPS (443)&lt;br&gt;• Auth: IAM + MFA&lt;br&gt;• Access: AWS Console&lt;br&gt;• Entry: Systems Manager&lt;br&gt;• Security: No SSH/RDP Ports&lt;br&gt;• Tools: Fleet, Session, CloudWatch, X-Ray" style="rounded=1;whiteSpace=wrap;html=1;align=left;verticalAlign=top;fillColor=#FFE6CC;strokeColor=#FF6600;fontSize=11" vertex="1" parent="1">
          <mxGeometry x="1320" y="800" width="520" height="120" as="geometry"/>
        </mxCell>
'''

def create_comparison_table():
    return '''        <!-- Comparison Table -->
        <mxCell id="table-title" value="ACCESS PATTERNS COMPARISON" style="text;html=1;strokeColor=none;fillColor=none;align=center;verticalAlign=middle;whiteSpace=wrap;rounded=0;fontSize=16;fontStyle=1" vertex="1" parent="1">
          <mxGeometry x="760" y="950" width="400" height="30" as="geometry"/>
        </mxCell>
        
        <mxCell id="table" value="&lt;table border=&quot;1&quot; style=&quot;width:100%;border-collapse:collapse;&quot;&gt;&lt;tr style=&quot;background:#f0f0f0;font-weight:bold;&quot;&gt;&lt;td&gt;Aspect&lt;/td&gt;&lt;td&gt;End User&lt;/td&gt;&lt;td&gt;IoT Device&lt;/td&gt;&lt;td&gt;Engineer&lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;&lt;b&gt;Protocol&lt;/b&gt;&lt;/td&gt;&lt;td&gt;HTTPS (443)&lt;/td&gt;&lt;td&gt;MQTT/TLS (8883)&lt;/td&gt;&lt;td&gt;HTTPS (443)&lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;&lt;b&gt;Auth&lt;/b&gt;&lt;/td&gt;&lt;td&gt;Cognito SSO&lt;/td&gt;&lt;td&gt;X.509 Certs&lt;/td&gt;&lt;td&gt;IAM + MFA&lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;&lt;b&gt;Entry&lt;/b&gt;&lt;/td&gt;&lt;td&gt;CloudFront&lt;/td&gt;&lt;td&gt;IoT Core&lt;/td&gt;&lt;td&gt;Systems Manager&lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;&lt;b&gt;Latency&lt;/b&gt;&lt;/td&gt;&lt;td&gt;&amp;lt;200ms&lt;/td&gt;&lt;td&gt;&amp;lt;50ms&lt;/td&gt;&lt;td&gt;&amp;lt;100ms&lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;&lt;b&gt;Purpose&lt;/b&gt;&lt;/td&gt;&lt;td&gt;Use Application&lt;/td&gt;&lt;td&gt;Send Telemetry&lt;/td&gt;&lt;td&gt;Troubleshoot&lt;/td&gt;&lt;/tr&gt;&lt;tr&gt;&lt;td&gt;&lt;b&gt;Pattern&lt;/b&gt;&lt;/td&gt;&lt;td&gt;Request/Response&lt;/td&gt;&lt;td&gt;Persistent&lt;/td&gt;&lt;td&gt;Interactive&lt;/td&gt;&lt;/tr&gt;&lt;/table&gt;" style="text;html=1;strokeColor=#666666;fillColor=#ffffff;align=left;verticalAlign=top;whiteSpace=wrap;rounded=1;fontSize=11" vertex="1" parent="1">
          <mxGeometry x="480" y="990" width="960" height="180" as="geometry"/>
        </mxCell>
'''

def create_footer():
    return '''      </root>
    </mxGraphModel>
  </diagram>
</mxfile>'''

def main():
    print("Generating Made4Net Access Patterns Diagram...")
    
    diagram_content = (
        create_drawio_header() +
        create_title() +
        create_section_headers() +
        create_end_user_flow() +
        create_iot_flow() +
        create_engineer_flow() +
        create_comparison_table() +
        create_footer()
    )
    
    with open('Made4Net-Access-Patterns-Complete.drawio', 'w', encoding='utf-8') as f:
        f.write(diagram_content)
    
    print("✓ Diagram created: Made4Net-Access-Patterns-Complete.drawio")
    print("  Size: {} bytes".format(len(diagram_content)))
    print("  Components:")
    print("    • End User Flow (Blue): User → CloudFront → ALB → EC2 → Cognito/RDS")
    print("    • IoT Device Flow (Green): Devices → IoT Core → Rules → Kinesis/Lambda/DynamoDB")
    print("    • Hosting Engineer Flow (Orange): Engineer → Console → Systems Manager → Tools")
    print("    • Comparison Table: All 3 patterns side-by-side")
    print("\n  Next: Open in draw.io to view and export as PNG/PDF")

if __name__ == '__main__':
    main()
