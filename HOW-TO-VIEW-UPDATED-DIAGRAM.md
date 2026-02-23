# How to View & Export Updated Architecture Diagram

## ✅ Diagram Already Updated!

The `Made4Net-AWS-Architecture.drawio` file has been updated with AWS Outposts components. Here's how to view and export it.

---

## 🎨 What Was Added to the Diagram

### Warehouse Examples (NEW!)

**Warehouse #1 (Chicago) - Standard Deployment**
- Blue box on the left side
- Traditional server icon
- Shows standard VPN connection to AWS
- Details: WMS Application, Barcode Scanners, Wi-Fi, VPN
- Connection: Blue dashed line (Site-to-Site VPN) to Transit Gateway

**Warehouse #2 (New York) - Outposts Deployment**
- Orange box on the left side
- AWS Outposts rack icon
- Shows service link connection to AWS
- Details: Outposts Rack, EC2, EBS, <10ms latency, Data Residency
- Connection: Orange dashed line (Service Link) to Transit Gateway

### AWS Outposts Section (Orange Section)

1. **AWS Outposts Box** (Orange container)
   - Label: "AWS Outposts (On-Premises Warehouses)"
   - Color: Orange (#FF6F00)
   - Location: Below Transit Gateway

2. **Outposts Rack Icon**
   - AWS Outposts rack symbol
   - Label: "Outposts Rack - Low Latency - Data Residency"

3. **EC2 on Outposts**
   - EC2 instance icon
   - Label: "EC2 on Outposts"

4. **EBS on Outposts**
   - EBS volume icon
   - Label: "EBS on Outposts"

5. **AWS Health Icon**
   - Health service icon
   - Label: "AWS Health Events"

### New Connections

- **Warehouse 1 → Transit Gateway:** Blue dashed line (Site-to-Site VPN)
- **Warehouse 2 → Transit Gateway:** Orange dashed line (Service Link for Outposts)
- **Service Link:** Transit Gateway → Outposts (orange dashed line)
- **Management:** Systems Manager → Outposts EC2 (purple dashed line)

### Updated Elements

- **Transit Gateway Label:** Now shows "800+ Warehouses + Outposts"
- **Legend:** Added orange entry for AWS Outposts

---

## 📖 Step-by-Step: View the Diagram

### Option 1: Online (Recommended)

1. **Go to draw.io website**
   ```
   https://app.diagrams.net/
   ```

2. **Open the file**
   - Click "Open Existing Diagram"
   - Navigate to your project folder
   - Select `Made4Net-AWS-Architecture.drawio`
   - Click "Open"

3. **View the updates**
   - Look for the **orange Outposts section** in the middle-right area
   - It's positioned below the Transit Gateway
   - Connected with orange dashed lines

### Option 2: Desktop App

1. **Download draw.io desktop**
   ```
   https://github.com/jgraph/drawio-desktop/releases
   ```

2. **Install and open**
   - Install the application
   - Open draw.io desktop
   - File → Open → Select `Made4Net-AWS-Architecture.drawio`

3. **View the updates**
   - Same as Option 1

---

## 📤 Step-by-Step: Export as PNG

### For Presentation/Document

1. **Open the diagram** (using Option 1 or 2 above)

2. **Adjust zoom** (optional)
   - Click View → Zoom
   - Select "Fit" or "100%" for best quality

3. **Export as PNG**
   - Click **File → Export as → PNG**
   
4. **Configure export settings**
   ```
   ✅ Zoom: 300% (for high quality)
   ✅ Border Width: 10
   ✅ Transparent Background: Unchecked
   ✅ Selection Only: Unchecked
   ✅ Include a copy of my diagram: Checked (optional)
   ```

5. **Save the file**
   - Filename: `Made4Net-AWS-Architecture-with-Outposts.png`
   - Location: Same folder as .drawio file
   - Click "Export"

6. **Verify the export**
   - Open the PNG file
   - Verify Outposts section is visible (orange box)
   - Check image quality is high

---

## 📄 Step-by-Step: Insert into HLD Document

### For Word Document

1. **Open HLD document**
   ```
   Made4Net-Operational-Excellence-HLD.docx
   ```

2. **Navigate to Section 7 or 8**
   - Look for "Architecture Diagrams" section
   - Or create a new section if needed

3. **Insert the PNG**
   - Click where you want the image
   - Insert → Pictures → This Device
   - Select `Made4Net-AWS-Architecture-with-Outposts.png`
   - Click "Insert"

4. **Resize and format**
   - Click the image
   - Drag corners to resize (maintain aspect ratio)
   - Right-click → Wrap Text → "In Line with Text" or "Square"
   - Center align if desired

5. **Add caption** (optional)
   ```
   Figure X: Made4Net Hybrid Architecture with AWS Outposts
   ```

---

## 🔍 What to Look For in the Diagram

### Visual Checklist

When you open the diagram, verify these elements are present:

**Warehouse Examples (Left Side):**
- [ ] **Blue box** for Warehouse #1 (Chicago) - Standard VPN
- [ ] **Orange box** for Warehouse #2 (New York) - Outposts
- [ ] **Blue dashed line** from Warehouse 1 to Transit Gateway
- [ ] **Orange dashed line** from Warehouse 2 to Transit Gateway

**AWS Outposts Section (Middle-Right):**
- [ ] **Orange Outposts box** in the middle-right area
- [ ] **Outposts Rack icon** inside the orange box
- [ ] **EC2 on Outposts icon** inside the orange box
- [ ] **EBS on Outposts icon** inside the orange box
- [ ] **AWS Health icon** inside the orange box
- [ ] **Orange dashed line** from Transit Gateway to Outposts (Service Link)
- [ ] **Purple dashed line** from Systems Manager to Outposts EC2
- [ ] **Updated Transit Gateway label** showing "+ Outposts"
- [ ] **Orange legend entry** at the bottom

---

## 🎨 Diagram Layout Overview

```
WAREHOUSE EXAMPLES (Left Side - Outside AWS Cloud)
┌─────────────────────┐
│ Warehouse #1        │ ──VPN──┐
│ (Chicago)           │        │
│ • Standard Deploy   │        │
│ • VPN Connection    │        │
└─────────────────────┘        │
                               │
┌─────────────────────┐        │
│ Warehouse #2        │ ──SL───┤
│ (New York)          │        │
│ • Outposts Deploy   │        │
│ • Service Link      │        │
└─────────────────────┘        │
                               ▼
┌─────────────────────────────────────────────────────────┐
│                    AWS CLOUD                            │
│                                                         │
│  [Internet]  [WAF]  [ALB]  [API GW]  [TGW] ◄───────────┤
│                                      │                  │
│                                      │ Service Link     │
│                                      ▼                  │
│  [EC2 ASG]  [Lambda]  [RDS]  [DynamoDB]  [S3]         │
│                                                         │
│                    ┌─────────────────────┐             │
│                    │  AWS OUTPOSTS       │ ◄── Orange  │
│                    │  • Outposts Rack    │             │
│                    │  • EC2 on Outposts  │             │
│                    │  • EBS on Outposts  │             │
│                    │  • AWS Health       │             │
│                    └─────────────────────┘             │
│                                                         │
│  [CloudWatch]  [GuardDuty]  [X-Ray]  [Config]         │
│                                                         │
│  [DR Region: us-west-2]                                │
│                                                         │
└─────────────────────────────────────────────────────────┘

Legend:
🔴 Layer 1: Perimeter
🔵 Layer 2: Compute
🟢 Layer 3: Data
🟠 Layer 4: Monitoring
🟧 AWS Outposts: Hybrid on-premises ◄── NEW
🔷 Warehouse Examples ◄── NEW
```

---

## 🖼️ Export Quality Settings

### For Different Use Cases

**For Presentation (PowerPoint/PDF):**
```
Zoom: 300%
Format: PNG
Border: 10px
Transparent: No
```

**For Printing:**
```
Zoom: 400%
Format: PNG or PDF
Border: 20px
Transparent: No
```

**For Web/Email:**
```
Zoom: 200%
Format: PNG
Border: 5px
Transparent: No
Compress: Yes
```

**For Document (Word):**
```
Zoom: 300%
Format: PNG
Border: 10px
Transparent: No
```

---

## 🔧 Troubleshooting

### Issue: Can't see Outposts section

**Solution:**
1. Make sure you opened the correct file: `Made4Net-AWS-Architecture.drawio`
2. Zoom out to see the full diagram (View → Zoom → Fit)
3. Look in the middle-right area, below Transit Gateway
4. The Outposts section is in an **orange box**

### Issue: Export is blurry

**Solution:**
1. Increase zoom to 300% or 400%
2. Use PNG format (not JPEG)
3. Don't resize the image after export
4. If inserting in Word, use "Insert Picture" not copy-paste

### Issue: Orange colors don't show

**Solution:**
1. Verify you're viewing the latest version of the file
2. Check file modification date (should be February 10, 2026)
3. Try opening in a different browser or the desktop app
4. Clear browser cache and reload

### Issue: File won't open

**Solution:**
1. Verify file is not corrupted (check file size > 20 KB)
2. Try opening in incognito/private browser window
3. Download draw.io desktop app
4. Check file extension is `.drawio` not `.xml`

---

## ✅ Verification Checklist

Before using the diagram, verify:

- [ ] Opened `Made4Net-AWS-Architecture.drawio` successfully
- [ ] Can see orange Outposts section
- [ ] All 5 Outposts components are visible
- [ ] Service link connection is visible
- [ ] Legend includes Outposts entry
- [ ] Exported PNG is high quality
- [ ] Image is suitable for presentation

---

## 📞 Quick Reference

**File Location:**
```
tsg-sandbox-pipeline/Made4Net-AWS-Architecture.drawio
```

**Online Editor:**
```
https://app.diagrams.net/
```

**Export Settings:**
```
Format: PNG
Zoom: 300%
Border: 10px
```

**What to Look For:**
```
Orange box labeled "AWS Outposts (On-Premises Warehouses)"
Located below Transit Gateway in the diagram
```

---

## 🎯 Next Steps

1. **Open the diagram** using draw.io (online or desktop)
2. **Verify Outposts section** is visible (orange box)
3. **Export as PNG** using 300% zoom
4. **Insert into HLD document** (optional)
5. **Use in presentation** to Sagi Van

---

**The diagram is ready! Just open it in draw.io to see the updates.** 🎨
