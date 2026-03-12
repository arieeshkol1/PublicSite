# How to Set Up Route 53 Records for www.eshkol.ai

## Current Setup
- S3 Bucket: `www.eshkol.ai`
- Static website hosting: Enabled
- S3 Website Endpoint: `www.eshkol.ai.s3-website-us-east-1.amazonaws.com`
- Hosted Zone ID: Z06481861W6WD32QMETRV

## Step-by-Step Instructions

### Step 1: Go to Route 53 Console
1. Open AWS Console: https://console.aws.amazon.com/route53/
2. Make sure you're in account: 991105135552
3. Click "Hosted zones" in the left menu
4. Click on "eshkol.ai"

### Step 2: Check Existing Records
You should see:
- NS record (nameservers)
- SOA record
- CNAME record for www.eshkol.ai (if it already exists)

### Step 3: Create or Update CNAME Record for www.eshkol.ai

#### If CNAME record already exists:
1. Click on the www.eshkol.ai CNAME record
2. Click "Edit record"
3. Verify these settings:
   - **Record name**: `www`
   - **Record type**: CNAME
   - **Value**: `www.eshkol.ai.s3-website-us-east-1.amazonaws.com`
   - **TTL**: 300 seconds
   - **Routing policy**: Simple routing
4. Click "Save changes"

#### If CNAME record does NOT exist:
1. Click "Create record"
2. Fill in:
   - **Record name**: `www`
   - **Record type**: CNAME - Routes traffic to another domain name
   - **Value**: `www.eshkol.ai.s3-website-us-east-1.amazonaws.com`
   - **TTL**: 300 seconds
   - **Routing policy**: Simple routing
3. Click "Create records"

### Step 4: Verify the Record
After creating/updating, you should see in your hosted zone:
```
Record name: www.eshkol.ai
Type: CNAME
Value: www.eshkol.ai.s3-website-us-east-1.amazonaws.com
TTL: 300
```

### Step 5: Update Nameservers at Your Registrar (CRITICAL!)

The Route 53 record alone is NOT enough. You MUST update nameservers at your domain registrar.

**Current nameservers (WRONG):**
- dns1.registrar-servers.com
- dns2.registrar-servers.com

**Required nameservers (CORRECT):**
- ns-1673.awsdns-17.co.uk
- ns-286.awsdns-35.com
- ns-690.awsdns-22.net
- ns-1252.awsdns-28.org

**How to update:**
1. Find where you registered eshkol.ai (check your email for purchase confirmation)
2. Log in to that registrar (likely Namecheap, GoDaddy, etc.)
3. Find eshkol.ai in your domain list
4. Change nameservers to the 4 AWS nameservers listed above
5. Save changes
6. Wait 1-2 hours for DNS propagation

### Step 6: Test After DNS Propagation

After 1-2 hours, test:

```powershell
# Check nameservers
nslookup -type=NS eshkol.ai 8.8.8.8
```
Should show AWS nameservers (ns-1673.awsdns-17.co.uk, etc.)

```powershell
# Check www subdomain
nslookup www.eshkol.ai 8.8.8.8
```
Should show: www.eshkol.ai.s3-website-us-east-1.amazonaws.com

```powershell
# Test the website
curl http://www.eshkol.ai
```
Should return your website HTML

## Common Issues

### Issue 1: "www.eshkol.ai doesn't resolve"
**Cause**: Nameservers at registrar are not pointing to Route 53
**Solution**: Update nameservers at your domain registrar (Step 5)

### Issue 2: "Changes not taking effect"
**Cause**: DNS propagation takes time
**Solution**: Wait 1-2 hours, clear DNS cache: `ipconfig /flushdns`

### Issue 3: "Can't find the registrar"
**Cause**: Domain registered elsewhere
**Solution**: Check email for "eshkol.ai purchase" or try logging into Namecheap.com

## Quick Reference

**S3 Website Endpoint:**
```
www.eshkol.ai.s3-website-us-east-1.amazonaws.com
```

**Route 53 Nameservers:**
```
ns-1673.awsdns-17.co.uk
ns-286.awsdns-35.com
ns-690.awsdns-22.net
ns-1252.awsdns-28.org
```

**CNAME Record:**
```
Name: www.eshkol.ai
Type: CNAME
Value: www.eshkol.ai.s3-website-us-east-1.amazonaws.com
TTL: 300
```

## Summary

1. ✓ Create CNAME record in Route 53 (you can do this now)
2. ⏳ Update nameservers at registrar (REQUIRED - you must do this)
3. ⏳ Wait for DNS propagation (1-2 hours)
4. ✓ Test and verify

The CNAME record in Route 53 is useless until you update the nameservers at your registrar!
