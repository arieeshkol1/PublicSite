# How to Export Draw.io Diagrams for HLD Document

## Quick Steps

### Option 1: Using draw.io Desktop App (Recommended)

1. **Download draw.io Desktop:**
   - Go to: https://www.diagrams.net/
   - Click "Download" → Choose Windows version
   - Install the application

2. **Open the Diagram:**
   - Launch draw.io Desktop
   - File → Open → Select `Made4Net-AWS-Architecture.drawio`

3. **Export as High-Quality PNG:**
   - File → Export as → PNG
   - Settings:
     - ✅ Transparent Background: OFF
     - ✅ Selection Only: OFF
     - ✅ Include a copy of my diagram: ON (optional)
     - Zoom: 300% (for high quality)
     - Border Width: 10
   - Click "Export"
   - Save as: `Made4Net-AWS-Architecture.png`

4. **Insert into Word Document:**
   - Open `Made4Net-Fortress-Factory-HLD.docx`
   - Go to Section 7 (Architecture Diagrams)
   - Find the red placeholder text
   - Insert → Pictures → Select `Made4Net-AWS-Architecture.png`
   - Resize to fit page width

### Option 2: Using draw.io Online (No Installation)

1. **Open draw.io Online:**
   - Go to: https://app.diagrams.net/

2. **Open the Diagram:**
   - Click "Open Existing Diagram"
   - Choose "Device" → Browse to `Made4Net-AWS-Architecture.drawio`
   - Click "Open"

3. **Export as PNG:**
   - File → Export as → PNG
   - Follow same settings as Option 1
   - Download the PNG file

4. **Insert into Word Document:**
   - Same as Option 1, step 4

## Both Diagrams to Export

### Diagram 1: Conceptual Architecture
**File:** `Made4Net-Fortress-Architecture.drawio`
**Best for:** High-level overview presentation
**Export as:** `Made4Net-Fortress-Architecture.png`

### Diagram 2: AWS Architecture with Real Icons
**File:** `Made4Net-AWS-Architecture.drawio`
**Best for:** Technical deep dive with Sagi Van
**Export as:** `Made4Net-AWS-Architecture.png`

## Recommended Export Settings

| Setting | Value | Why |
|---------|-------|-----|
| Format | PNG | Best for Word documents |
| Zoom | 300% | High quality for printing |
| Transparent Background | OFF | Better for presentations |
| Border Width | 10 | Clean edges |
| DPI | 300 | Print quality |

## Tips for Best Results

1. **For Presentations:**
   - Export at 300% zoom
   - Use white background (not transparent)
   - Save as PNG format

2. **For Printing:**
   - Export at 400% zoom
   - Ensure all text is readable
   - Test print one page first

3. **For Email/Sharing:**
   - Export at 200% zoom (smaller file size)
   - PNG format for compatibility

## Inserting into PowerPoint (Alternative)

If you prefer PowerPoint over Word:

1. Create new PowerPoint presentation
2. Insert → Pictures → Select exported PNG
3. Add title slide with:
   - "Made4Net Fortress & Factory Architecture"
   - "Prepared for: Sagi Van"
   - Your name and credentials

## Troubleshooting

### Issue: Diagram looks blurry in Word
**Solution:** Re-export at higher zoom (400% or 500%)

### Issue: File size too large
**Solution:** Export at lower zoom (200%) or use JPEG format

### Issue: AWS icons not showing
**Solution:** The icons are embedded in the draw.io file. If they don't show:
- Ensure you have internet connection when opening draw.io
- The AWS icon library loads automatically

### Issue: Can't open .drawio file
**Solution:** 
- Use draw.io Desktop app (recommended)
- Or use online version at app.diagrams.net
- .drawio files are XML format, viewable in any text editor

## Quick Reference: File Locations

```
C:\Users\Michal\Desktop\Career\TSG_Demo2\Final Materials\tsg-sandbox-pipeline\
├── Made4Net-Fortress-Factory-HLD.docx          ← Insert diagrams here
├── Made4Net-AWS-Architecture.drawio            ← Export this (main diagram)
├── Made4Net-Fortress-Architecture.drawio       ← Export this (conceptual)
└── MADE4NET-DELIVERABLES-SUMMARY.md           ← Read this first
```

## Final Checklist

Before presenting to Sagi Van:

- [ ] Export both diagrams as PNG (300% zoom)
- [ ] Insert diagrams into Word document Section 7
- [ ] Remove red placeholder text
- [ ] Review all talking points in Section 3
- [ ] Print one copy to test quality
- [ ] Save final version as PDF (optional)

---

**Need Help?**
- draw.io documentation: https://www.diagrams.net/doc/
- AWS Architecture Icons: https://aws.amazon.com/architecture/icons/
