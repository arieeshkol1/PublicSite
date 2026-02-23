#!/usr/bin/env python3
"""
Made4Net Access Patterns Diagram Generator
Creates a comprehensive diagram showing:
1. End User Access (Tenant Login)
2. IoT Device Access (Robots/Sensors)
3. Hosting Engineer Access (Troubleshooting)
"""

import xml.etree.ElementTree as ET
from datetime import datetime

def create_access_patterns_diagram():
    """Generate the access patterns diagram in draw.io XML format"""
    
    # Read the baseline diagram
    with open('Made4Net-AWS-Architecture.drawio', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Parse XML
    root = ET.fromstring(content)
    
    # Update diagram name
    for diagram in root.findall('.//diagram'):
        diagram.set('name', 'Made4Net-Access-Patterns')
    
    # Update title in mxGraphModel
    for cell in root.findall('.//mxCell'):
        value = cell.get('value', '')
        if 'Made4Net' in value and 'Architecture' in value:
            cell.set('value', 'Made4Net Access Patterns & User Flows')
    
    # Write the new diagram
    tree = ET.ElementTree(root)
    ET.indent(tree, space='  ')
    tree.write('Made4Net-Access-Patterns.drawio', 
               encoding='utf-8', 
               xml_declaration=True)
    
    print("✓ Access Patterns diagram created: Made4Net-Access-Patterns.drawio")
    print("  Based on: Made4Net-AWS-Architecture.drawio")
    print("  Next: Open in draw.io and add access pattern flows")

if __name__ == '__main__':
    create_access_patterns_diagram()
