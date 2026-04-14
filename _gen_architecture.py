"""
Generate SlashMyCloudBill Architecture diagram (PublicSite.drawio)
Run: python _gen_architecture.py
Then open PublicSite.drawio in draw.io
"""

xml = '''<?xml version="1.0" encoding="UTF-8"?>
<mxfile host="app.diagrams.net" agent="kiro">
  <diagram name="SlashMyCloudBill Architecture" id="smb-arch">
    <mxGraphModel dx="1800" dy="1100" grid="1" gridSize="10" guides="1" tooltips="1" connect="1" arrows="1" fold="1" page="0" pageScale="1" pageWidth="1600" pageHeight="1000">
      <root>
        <mxCell id="0"/>
        <mxCell id="1" parent="0"/>

        <!-- Title -->
        <mxCell id="title" value="SlashMyCloudBill — Full Architecture" style="text;html=1;strokeColor=none;fillColor=none;align=center;fontSize=20;fontStyle=1;fontColor=#232F3E;" vertex="1" parent="1">
          <mxGeometry x="400" y="10" width="600" height="40" as="geometry"/>
        </mxCell>

        <!-- User -->
        <mxCell id="user" value="User&#xa;(Browser)" style="sketch=0;outlineConnect=0;fontColor=#232F3E;fillColor=#232F3E;strokeColor=#232F3E;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=11;fontStyle=0;aspect=fixed;pointerEvents=1;shape=mxgraph.aws4.user;" vertex="1" parent="1">
          <mxGeometry x="50" y="300" width="50" height="50" as="geometry"/>
        </mxCell>

        <!-- Route 53 -->
        <mxCell id="r53" value="Route 53&#xa;slashmycloudbill.com" style="sketch=0;points=[[0,0,0],[0.25,0,0],[0.5,0,0],[0.75,0,0],[1,0,0],[0,1,0],[0.25,1,0],[0.5,1,0],[0.75,1,0],[1,1,0]];outlineConnect=0;fontColor=#232F3E;fillColor=#8C4FFF;strokeColor=#ffffff;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=11;fontStyle=0;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.route_53;" vertex="1" parent="1">
          <mxGeometry x="200" y="300" width="50" height="50" as="geometry"/>
        </mxCell>

        <!-- CloudFront SMB -->
        <mxCell id="cf-smb" value="CloudFront&#xa;E2B3GXE4TJTH4Q" style="sketch=0;points=[[0,0,0],[0.25,0,0],[0.5,0,0],[0.75,0,0],[1,0,0],[0,1,0],[0.25,1,0],[0.5,1,0],[0.75,1,0],[1,1,0]];outlineConnect=0;fontColor=#232F3E;fillColor=#8C4FFF;strokeColor=#ffffff;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=11;fontStyle=0;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.cloudfront;" vertex="1" parent="1">
          <mxGeometry x="370" y="200" width="50" height="50" as="geometry"/>
        </mxCell>

        <!-- S3 SMB Bucket -->
        <mxCell id="s3-smb" value="S3 Bucket&#xa;slashmycloudbill.com" style="sketch=0;points=[[0,0,0],[0.25,0,0],[0.5,0,0],[0.75,0,0],[1,0,0],[0,1,0],[0.25,1,0],[0.5,1,0],[0.75,1,0],[1,1,0]];outlineConnect=0;fontColor=#232F3E;fillColor=#7AA116;strokeColor=#ffffff;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=11;fontStyle=0;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.s3;" vertex="1" parent="1">
          <mxGeometry x="550" y="200" width="50" height="50" as="geometry"/>
        </mxCell>

        <!-- API Gateway -->
        <mxCell id="apigw" value="API Gateway&#xa;ViewMyBill-API" style="sketch=0;points=[[0,0,0],[0.25,0,0],[0.5,0,0],[0.75,0,0],[1,0,0],[0,1,0],[0.25,1,0],[0.5,1,0],[0.75,1,0],[1,1,0]];outlineConnect=0;fontColor=#232F3E;fillColor=#E7157B;strokeColor=#ffffff;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=11;fontStyle=0;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.api_gateway;" vertex="1" parent="1">
          <mxGeometry x="370" y="400" width="50" height="50" as="geometry"/>
        </mxCell>

        <!-- Lambda: Bill Analyzer -->
        <mxCell id="lambda-bill" value="Bill Analyzer&#xa;Lambda" style="sketch=0;points=[[0,0,0],[0.25,0,0],[0.5,0,0],[0.75,0,0],[1,0,0],[0,1,0],[0.25,1,0],[0.5,1,0],[0.75,1,0],[1,1,0]];outlineConnect=0;fontColor=#232F3E;fillColor=#ED7100;strokeColor=#ffffff;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=11;fontStyle=0;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.lambda;" vertex="1" parent="1">
          <mxGeometry x="550" y="370" width="50" height="50" as="geometry"/>
        </mxCell>

        <!-- Lambda: Upload Handler -->
        <mxCell id="lambda-upload" value="Upload Handler&#xa;Lambda" style="sketch=0;points=[[0,0,0],[0.25,0,0],[0.5,0,0],[0.75,0,0],[1,0,0],[0,1,0],[0.25,1,0],[0.5,1,0],[0.75,1,0],[1,1,0]];outlineConnect=0;fontColor=#232F3E;fillColor=#ED7100;strokeColor=#ffffff;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=11;fontStyle=0;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.lambda;" vertex="1" parent="1">
          <mxGeometry x="550" y="440" width="50" height="50" as="geometry"/>
        </mxCell>

        <!-- Lambda: OTP Handler -->
        <mxCell id="lambda-otp" value="OTP Handler&#xa;Lambda" style="sketch=0;points=[[0,0,0],[0.25,0,0],[0.5,0,0],[0.75,0,0],[1,0,0],[0,1,0],[0.25,1,0],[0.5,1,0],[0.75,1,0],[1,1,0]];outlineConnect=0;fontColor=#232F3E;fillColor=#ED7100;strokeColor=#ffffff;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=11;fontStyle=0;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.lambda;" vertex="1" parent="1">
          <mxGeometry x="700" y="370" width="50" height="50" as="geometry"/>
        </mxCell>

        <!-- Lambda: Member Handler -->
        <mxCell id="lambda-member" value="Member Handler&#xa;Lambda" style="sketch=0;points=[[0,0,0],[0.25,0,0],[0.5,0,0],[0.75,0,0],[1,0,0],[0,1,0],[0.25,1,0],[0.5,1,0],[0.75,1,0],[1,1,0]];outlineConnect=0;fontColor=#232F3E;fillColor=#ED7100;strokeColor=#ffffff;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=11;fontStyle=0;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.lambda;" vertex="1" parent="1">
          <mxGeometry x="700" y="440" width="50" height="50" as="geometry"/>
        </mxCell>

        <!-- Lambda: Admin Handler -->
        <mxCell id="lambda-admin" value="Admin Handler&#xa;Lambda" style="sketch=0;points=[[0,0,0],[0.25,0,0],[0.5,0,0],[0.75,0,0],[1,0,0],[0,1,0],[0.25,1,0],[0.5,1,0],[0.75,1,0],[1,1,0]];outlineConnect=0;fontColor=#232F3E;fillColor=#ED7100;strokeColor=#ffffff;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=11;fontStyle=0;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.lambda;" vertex="1" parent="1">
          <mxGeometry x="850" y="370" width="50" height="50" as="geometry"/>
        </mxCell>

        <!-- Bedrock -->
        <mxCell id="bedrock" value="Amazon Bedrock&#xa;Nova 2 Lite" style="sketch=0;points=[[0,0,0],[0.25,0,0],[0.5,0,0],[0.75,0,0],[1,0,0],[0,1,0],[0.25,1,0],[0.5,1,0],[0.75,1,0],[1,1,0]];outlineConnect=0;fontColor=#232F3E;fillColor=#01A88D;strokeColor=#ffffff;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=11;fontStyle=0;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.sagemaker;" vertex="1" parent="1">
          <mxGeometry x="550" y="580" width="50" height="50" as="geometry"/>
        </mxCell>

        <!-- Cognito -->
        <mxCell id="cognito" value="Cognito&#xa;User Pool" style="sketch=0;points=[[0,0,0],[0.25,0,0],[0.5,0,0],[0.75,0,0],[1,0,0],[0,1,0],[0.25,1,0],[0.5,1,0],[0.75,1,0],[1,1,0]];outlineConnect=0;fontColor=#232F3E;fillColor=#DD344C;strokeColor=#ffffff;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=11;fontStyle=0;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.cognito;" vertex="1" parent="1">
          <mxGeometry x="700" y="580" width="50" height="50" as="geometry"/>
        </mxCell>

        <!-- DynamoDB -->
        <mxCell id="ddb" value="DynamoDB&#xa;(6 tables)" style="sketch=0;points=[[0,0,0],[0.25,0,0],[0.5,0,0],[0.75,0,0],[1,0,0],[0,1,0],[0.25,1,0],[0.5,1,0],[0.75,1,0],[1,1,0]];outlineConnect=0;fontColor=#232F3E;fillColor=#C925D1;strokeColor=#ffffff;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=11;fontStyle=0;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.dynamodb;" vertex="1" parent="1">
          <mxGeometry x="850" y="580" width="50" height="50" as="geometry"/>
        </mxCell>

        <!-- SES -->
        <mxCell id="ses" value="SES&#xa;Email" style="sketch=0;points=[[0,0,0],[0.25,0,0],[0.5,0,0],[0.75,0,0],[1,0,0],[0,1,0],[0.25,1,0],[0.5,1,0],[0.75,1,0],[1,1,0]];outlineConnect=0;fontColor=#232F3E;fillColor=#DD344C;strokeColor=#ffffff;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=11;fontStyle=0;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.simple_email_service;" vertex="1" parent="1">
          <mxGeometry x="1000" y="400" width="50" height="50" as="geometry"/>
        </mxCell>

        <!-- S3 Storage -->
        <mxCell id="s3-storage" value="S3 Storage&#xa;Bills + Reports" style="sketch=0;points=[[0,0,0],[0.25,0,0],[0.5,0,0],[0.75,0,0],[1,0,0],[0,1,0],[0.25,1,0],[0.5,1,0],[0.75,1,0],[1,1,0]];outlineConnect=0;fontColor=#232F3E;fillColor=#7AA116;strokeColor=#ffffff;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=11;fontStyle=0;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.s3;" vertex="1" parent="1">
          <mxGeometry x="1000" y="200" width="50" height="50" as="geometry"/>
        </mxCell>

        <!-- STS -->
        <mxCell id="sts" value="STS&#xa;AssumeRole" style="sketch=0;points=[[0,0,0],[0.25,0,0],[0.5,0,0],[0.75,0,0],[1,0,0],[0,1,0],[0.25,1,0],[0.5,1,0],[0.75,1,0],[1,1,0]];outlineConnect=0;fontColor=#232F3E;fillColor=#DD344C;strokeColor=#ffffff;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=11;fontStyle=0;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.role;" vertex="1" parent="1">
          <mxGeometry x="1000" y="580" width="50" height="50" as="geometry"/>
        </mxCell>

        <!-- Customer AWS Account -->
        <mxCell id="cust-aws" value="Customer&#xa;AWS Account" style="sketch=0;outlineConnect=0;fontColor=#232F3E;fillColor=#232F3E;strokeColor=#232F3E;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=11;fontStyle=0;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.general_AWS_cloud;" vertex="1" parent="1">
          <mxGeometry x="1200" y="400" width="50" height="50" as="geometry"/>
        </mxCell>

        <!-- GitHub Actions -->
        <mxCell id="github" value="GitHub Actions&#xa;CI/CD" style="sketch=0;outlineConnect=0;fontColor=#232F3E;fillColor=#232F3E;strokeColor=#232F3E;dashed=0;verticalLabelPosition=bottom;verticalAlign=top;align=center;html=1;fontSize=11;fontStyle=0;aspect=fixed;shape=mxgraph.aws4.resourceIcon;resIcon=mxgraph.aws4.codecommit;" vertex="1" parent="1">
          <mxGeometry x="550" y="80" width="50" height="50" as="geometry"/>
        </mxCell>

        <!-- Connections -->
        <mxCell id="e1" style="edgeStyle=orthogonalEdgeStyle;" edge="1" source="user" target="r53" parent="1"><mxGeometry relative="1" as="geometry"/></mxCell>
        <mxCell id="e2" style="edgeStyle=orthogonalEdgeStyle;" edge="1" source="r53" target="cf-smb" parent="1"><mxGeometry relative="1" as="geometry"/></mxCell>
        <mxCell id="e3" style="edgeStyle=orthogonalEdgeStyle;" edge="1" source="cf-smb" target="s3-smb" parent="1"><mxGeometry relative="1" as="geometry"/></mxCell>
        <mxCell id="e4" style="edgeStyle=orthogonalEdgeStyle;" edge="1" source="user" target="apigw" parent="1"><mxGeometry relative="1" as="geometry"/></mxCell>
        <mxCell id="e5" style="edgeStyle=orthogonalEdgeStyle;" edge="1" source="apigw" target="lambda-bill" parent="1"><mxGeometry relative="1" as="geometry"/></mxCell>
        <mxCell id="e6" style="edgeStyle=orthogonalEdgeStyle;" edge="1" source="apigw" target="lambda-upload" parent="1"><mxGeometry relative="1" as="geometry"/></mxCell>
        <mxCell id="e7" style="edgeStyle=orthogonalEdgeStyle;" edge="1" source="apigw" target="lambda-otp" parent="1"><mxGeometry relative="1" as="geometry"/></mxCell>
        <mxCell id="e8" style="edgeStyle=orthogonalEdgeStyle;" edge="1" source="apigw" target="lambda-member" parent="1"><mxGeometry relative="1" as="geometry"/></mxCell>
        <mxCell id="e9" style="edgeStyle=orthogonalEdgeStyle;" edge="1" source="apigw" target="lambda-admin" parent="1"><mxGeometry relative="1" as="geometry"/></mxCell>
        <mxCell id="e10" style="edgeStyle=orthogonalEdgeStyle;" edge="1" source="lambda-bill" target="bedrock" parent="1"><mxGeometry relative="1" as="geometry"/></mxCell>
        <mxCell id="e11" style="edgeStyle=orthogonalEdgeStyle;" edge="1" source="lambda-member" target="cognito" parent="1"><mxGeometry relative="1" as="geometry"/></mxCell>
        <mxCell id="e12" style="edgeStyle=orthogonalEdgeStyle;" edge="1" source="lambda-member" target="ddb" parent="1"><mxGeometry relative="1" as="geometry"/></mxCell>
        <mxCell id="e13" style="edgeStyle=orthogonalEdgeStyle;" edge="1" source="lambda-otp" target="ses" parent="1"><mxGeometry relative="1" as="geometry"/></mxCell>
        <mxCell id="e14" style="edgeStyle=orthogonalEdgeStyle;" edge="1" source="lambda-upload" target="s3-storage" parent="1"><mxGeometry relative="1" as="geometry"/></mxCell>
        <mxCell id="e15" style="edgeStyle=orthogonalEdgeStyle;" edge="1" source="lambda-member" target="sts" parent="1"><mxGeometry relative="1" as="geometry"/></mxCell>
        <mxCell id="e16" style="edgeStyle=orthogonalEdgeStyle;" edge="1" source="sts" target="cust-aws" parent="1"><mxGeometry relative="1" as="geometry"/></mxCell>
        <mxCell id="e17" style="edgeStyle=orthogonalEdgeStyle;" edge="1" source="github" target="s3-smb" parent="1"><mxGeometry relative="1" as="geometry"/></mxCell>
        <mxCell id="e18" style="edgeStyle=orthogonalEdgeStyle;" edge="1" source="lambda-admin" target="ddb" parent="1"><mxGeometry relative="1" as="geometry"/></mxCell>
        <mxCell id="e19" style="edgeStyle=orthogonalEdgeStyle;" edge="1" source="lambda-bill" target="s3-storage" parent="1"><mxGeometry relative="1" as="geometry"/></mxCell>
        <mxCell id="e20" style="edgeStyle=orthogonalEdgeStyle;" edge="1" source="lambda-otp" target="ddb" parent="1"><mxGeometry relative="1" as="geometry"/></mxCell>

      </root>
    </mxGraphModel>
  </diagram>
</mxfile>'''

with open('PublicSite.drawio', 'w', encoding='utf-8') as f:
    f.write(xml)

print("PublicSite.drawio generated - open in draw.io")
