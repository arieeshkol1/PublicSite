# CRITICAL: Fix Domain Nameservers

## Problem
Your domain `eshkol.ai` nameservers are pointing to the registrar's nameservers instead of AWS Route 53.

**Current nameservers (WRONG):**
- dns1.registrar-servers.com
- dns2.registrar-servers.com

**Required nameservers (CORRECT):**
- ns-1673.awsdns-17.co.uk
- ns-286.awsdns-35.com
- ns-690.awsdns-22.net
- ns-1252.awsdns-28.org

## Why www.eshkol.ai is not working
- The S3 bucket and website are working fine (tested successfully)
- Route 53 has the correct CNAME record configured
- BUT: DNS queries are going to the registrar's nameservers, not Route 53
- The registrar's nameservers don't have your DNS records

## How to Fix

### Step 1: Find Your Domain Registrar
Your domain is registered with a registrar (where you bought the domain). Common registrars:
- Namecheap
- GoDaddy
- Google Domains
- Cloudflare
- Name.com
- Hover
- etc.

### Step 2: Update Nameservers at Registrar

1. Log in to your domain registrar's website
2. Find your domain `eshkol.ai`
3. Look for "Nameservers", "DNS Settings", or "Name Server Settings"
4. Change from "Default" or "Registrar Nameservers" to "Custom Nameservers"
5. Enter these 4 nameservers:
   ```
   ns-1673.awsdns-17.co.uk
   ns-286.awsdns-35.com
   ns-690.awsdns-22.net
   ns-1252.awsdns-28.org
   ```
6. Save the changes

### Step 3: Wait for DNS Propagation
- Nameserver changes can take 24-48 hours to propagate globally
- Usually happens within 1-2 hours
- You can check progress with: `nslookup -type=NS eshkol.ai 8.8.8.8`

### Step 4: Verify
After propagation, run:
```powershell
nslookup -type=NS eshkol.ai 8.8.8.8
```

Should show:
```
eshkol.ai       nameserver = ns-1673.awsdns-17.co.uk
eshkol.ai       nameserver = ns-286.awsdns-35.com
eshkol.ai       nameserver = ns-690.awsdns-22.net
eshkol.ai       nameserver = ns-1252.awsdns-28.org
```

Then test:
```powershell
nslookup www.eshkol.ai
```

Should resolve to: `www.eshkol.ai.s3-website-us-east-1.amazonaws.com`

## Common Registrar Instructions

### Namecheap
1. Log in to Namecheap
2. Go to Domain List
3. Click "Manage" next to eshkol.ai
4. Find "Nameservers" section
5. Select "Custom DNS"
6. Enter the 4 AWS nameservers
7. Click the green checkmark to save

### GoDaddy
1. Log in to GoDaddy
2. Go to My Products
3. Click DNS next to eshkol.ai
4. Scroll to "Nameservers"
5. Click "Change"
6. Select "Enter my own nameservers (advanced)"
7. Enter the 4 AWS nameservers
8. Click "Save"

### Google Domains
1. Log in to Google Domains
2. Click on eshkol.ai
3. Click "DNS" in the left menu
4. Scroll to "Name servers"
5. Click "Use custom name servers"
6. Enter the 4 AWS nameservers
7. Click "Save"

### Cloudflare
1. Log in to Cloudflare
2. Select eshkol.ai
3. Go to DNS settings
4. Change nameservers to the 4 AWS nameservers
5. Save changes

## After Nameservers Are Updated

Once the nameservers are pointing to Route 53:
- http://www.eshkol.ai will work automatically (CNAME record already configured)
- http://eshkol.ai will work once the bucket name is available and redirect is set up

## Current Status Check
Run this to check current nameservers:
```powershell
nslookup -type=NS eshkol.ai 8.8.8.8
```

Run this to check if www subdomain resolves:
```powershell
nslookup www.eshkol.ai 8.8.8.8
```
