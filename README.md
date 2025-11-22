# S3 Cache-Control Manager

A robust Python script to manage Cache-Control headers for S3 objects with advanced filtering, backup, and revert capabilities.

## Features

✅ **Flexible Filtering**
- Filter by folder/directory prefix
- Filter by filename patterns
- Extension-based filtering (images/SVGs by default)
- Option to process all file types

✅ **Safety Features**
- Dry-run mode to preview changes
- Automatic backup creation
- Revert capability using backup files
- Confirmation prompts

✅ **Performance**
- Parallel processing with configurable workers
- Efficient S3 copy operations (no downloads)
- Progress tracking for large buckets

✅ **Error Handling**
- Comprehensive error reporting
- Graceful handling of missing/inaccessible objects
- AWS credential verification

## Requirements

```bash
pip install boto3
```

## 🛠️ Installation

### Option 1: Clone the repository

```bash
git clone https://github.com/shimiljascf/s3-cache-update.git
cd s3-cache-update
pip install -r requirements.txt
```

### Option 2: Direct download

```bash
curl -O https://raw.githubusercontent.com/shimiljascf/s3-cache-update/master/s3_cache_control_manager.py
pip install boto3
```


## AWS Credentials Setup

Configure AWS credentials using one of these methods:

```bash
# Method 1: AWS CLI
aws configure

# Method 2: Environment variables
export AWS_ACCESS_KEY_ID="your-key"
export AWS_SECRET_ACCESS_KEY="your-secret"
export AWS_DEFAULT_REGION="us-east-1"

# Method 3: IAM role (if running on EC2/ECS)
# Automatically uses instance IAM role
```

### Required IAM Permissions

```json
{
  "Version": "2012-10-17",
  "Statement": [
    {
      "Effect": "Allow",
      "Action": [
        "s3:ListBucket",
        "s3:HeadBucket"
      ],
      "Resource": "arn:aws:s3:::your-bucket-name"
    },
    {
      "Effect": "Allow",
      "Action": [
        "s3:GetObject",
        "s3:GetObjectMetadata",
        "s3:PutObject",
        "s3:CopyObject"
      ],
      "Resource": "arn:aws:s3:::your-bucket-name/*"
    }
  ]
}
```

## Usage

### Basic Commands

```bash
# View help
python s3_cache_control_manager.py --help
python s3_cache_control_manager.py update --help
python s3_cache_control_manager.py revert --help
```

### 1. Update All Images in Bucket

```bash
# Default: Updates only image and SVG files
python s3_cache_control_manager.py update --bucket my-bucket
```

**What this does:**
- Processes files with extensions: .jpg, .jpeg, .png, .gif, .webp, .bmp, .ico, .svg, .tiff, .tif, .avif, .heic, .heif
- Skips: .html, .htm, .css, .js, .json, .xml, .txt files
- Sets Cache-Control: `public, max-age=31536000, immutable`
- Creates backup file in `.s3_cache_backups/` directory

### 2. Update Specific Folder(s)

```bash
# Single folder
python s3_cache_control_manager.py update \
  --bucket my-bucket \
  --folder assets/images/

# Multiple folders
python s3_cache_control_manager.py update \
  --bucket my-bucket \
  --folder assets/images/ icons/ static/media/
```

**What this does:**
- Only processes files within specified folder prefix(es)
- Example: `--folder assets/images/` matches:
  - ✓ `assets/images/logo.png`
  - ✓ `assets/images/banners/hero.jpg`
  - ✗ `assets/icons/favicon.ico`

### 3. Update Specific Files by Name

```bash
# Files containing "logo" in filename
python s3_cache_control_manager.py update \
  --bucket my-bucket \
  --file logo

# Multiple patterns
python s3_cache_control_manager.py update \
  --bucket my-bucket \
  --file logo banner icon
```

**What this does:**
- Matches filenames containing the specified patterns
- Example: `--file logo` matches:
  - ✓ `assets/logo.png`
  - ✓ `images/company-logo-dark.svg`
  - ✗ `assets/banner.jpg`

### 4. Combine Folder and File Filters

```bash
python s3_cache_control_manager.py update \
  --bucket my-bucket \
  --folder assets/ \
  --file logo icon
```

**What this does:**
- Files must match BOTH folder AND file filters
- Example matches:
  - ✓ `assets/logo.png`
  - ✓ `assets/icons/favicon.ico`
  - ✗ `static/logo.png` (wrong folder)
  - ✗ `assets/banner.jpg` (wrong filename)

### 5. Update All File Types (Disable Extension Filter)

```bash
python s3_cache_control_manager.py update \
  --bucket my-bucket \
  --no-extension-filter
```

**What this does:**
- Processes ALL files regardless of extension
- Includes HTML, CSS, JS, etc.
- Use with caution - may affect website functionality

### 6. Custom Cache-Control Header

```bash
python s3_cache_control_manager.py update \
  --bucket my-bucket \
  --cache-control "public, max-age=86400"
```

**Common Cache-Control values:**
- `public, max-age=31536000, immutable` - Static assets (1 year)
- `public, max-age=86400` - Daily updates (24 hours)
- `public, max-age=3600` - Hourly updates (1 hour)
- `no-cache` - Always revalidate
- `private, max-age=0, no-cache` - No caching

### 7. Dry Run (Preview Changes)

```bash
python s3_cache_control_manager.py update \
  --bucket my-bucket \
  --folder assets/ \
  --dry-run
```

**What this does:**
- Shows what WOULD be changed without making actual changes
- Displays current Cache-Control values
- Creates no backup file
- Safe to run multiple times

### 8. Skip Confirmation Prompt

```bash
python s3_cache_control_manager.py update \
  --bucket my-bucket \
  --yes
```

**What this does:**
- Proceeds without asking for confirmation
- Useful for automation/scripts
- Use with caution

### 9. Adjust Performance

```bash
# Increase parallelism for large buckets
python s3_cache_control_manager.py update \
  --bucket my-bucket \
  --max-workers 20

# Reduce for rate limiting or slower connections
python s3_cache_control_manager.py update \
  --bucket my-bucket \
  --max-workers 5
```

### 10. Revert Changes

```bash
# Revert using backup file
python s3_cache_control_manager.py revert \
  --bucket my-bucket \
  --backup .s3_cache_backups/my-bucket_update_20250110_143052.json

# Dry run revert (preview)
python s3_cache_control_manager.py revert \
  --bucket my-bucket \
  --backup .s3_cache_backups/my-bucket_update_20250110_143052.json \
  --dry-run
```

**What this does:**
- Restores original Cache-Control values from backup
- Restores all original metadata (Content-Type, etc.)
- Can be dry-run first to verify

## Logic Verification

### File Processing Logic

The script uses the following decision flow:

```
For each S3 object:
│
├─ Is key empty or ends with '/'? → SKIP (directory marker)
│
├─ Apply folder filters (if specified):
│  └─ Does key start with any folder prefix? → NO → SKIP
│
├─ Apply file filters (if specified):
│  └─ Does filename contain any pattern? → NO → SKIP
│
├─ Apply extension filter (if enabled):
│  ├─ Is extension in SKIP list? → YES → SKIP
│  └─ Is extension in ALLOWED list? → NO → SKIP
│
└─ All checks passed → PROCESS
```

### Extension Filter Logic

**Default behavior (extension filter enabled):**
- ALLOWED: `.jpg`, `.jpeg`, `.png`, `.gif`, `.webp`, `.bmp`, `.ico`, `.svg`, `.tiff`, `.tif`, `.avif`, `.heic`, `.heif`
- SKIPPED: `.html`, `.htm`, `.css`, `.js`, `.json`, `.xml`, `.txt`
- OTHER: Any other extension is skipped by default

**With `--no-extension-filter`:**
- ALL files are processed regardless of extension

### Cache-Control Update Logic

```
For each object to process:
│
├─ Fetch current metadata (head-object)
│  └─ Object not found/accessible? → ERROR
│
├─ Is current Cache-Control already correct?
│  └─ YES → SKIP (no change needed)
│
├─ In dry-run mode?
│  └─ YES → Report what would change, SKIP actual update
│
└─ Perform copy-object with new Cache-Control
   ├─ Preserve all existing metadata
   ├─ Preserve Content-Type
   ├─ Preserve Content-Encoding, Language, Disposition
   └─ Store backup data for revert
```

### Backup Logic

**Backup creation:**
- Happens during update operation (unless `--no-backup` specified)
- Stores: Key, Current Cache-Control, Content-Type, Metadata, Encodings
- Saved as timestamped JSON file
- One backup file per update operation

**Backup usage:**
- Used by revert operation
- Validates objects still exist before reverting
- Restores exact original metadata

### Safety Checks

1. **AWS Credential Verification:**
   - Checks bucket access before starting
   - Fails fast if credentials are invalid

2. **Confirmation Prompts:**
   - Shows what will be changed
   - Requires explicit confirmation (unless `--yes` used)
   - Separate for update and revert operations

3. **Error Handling:**
   - Individual object errors don't stop the batch
   - All errors are reported at the end
   - Exit code 1 if any errors occurred

4. **Parallel Processing Safety:**
   - Thread-safe S3 operations
   - Progress tracking with atomic counters
   - Graceful handling of exceptions in workers

## Output Examples

### Successful Update

```
======================================================================
S3 Cache-Control Update Operation
======================================================================

Bucket: my-bucket
Cache-Control: public, max-age=31536000, immutable
Dry Run Mode: DISABLED
Max Workers: 10
Folder Filters: assets/images/

Verifying AWS credentials and bucket access...
✓ Credentials verified

Listing all objects in bucket...
✓ Found 1,234 objects

Filtering objects...

✓ Objects to update: 156
✓ Objects skipped: 1,078

Skip reasons:
  - Does not match folder filter: 892
  - Skipped extension: .js: 124
  - Skipped extension: .html: 62

⚠️  About to update Cache-Control for 156 objects.
Continue? (yes/no): yes

Processing objects...

[1/156] ✓ assets/images/logo.png
[2/156] ✓ assets/images/banner.jpg
[3/156] ⊘ assets/images/icon.svg (Already has correct Cache-Control)
...
[156/156] ✓ assets/images/footer-bg.webp

✓ Backup saved to: .s3_cache_backups/my-bucket_update_20250110_143052.json

💾 To revert these changes, run:
   python s3_cache_control_manager.py revert --bucket my-bucket --backup .s3_cache_backups/my-bucket_update_20250110_143052.json

======================================================================
Update Complete!
======================================================================
Total objects in bucket: 1,234
Objects processed: 156
Successful updates: 153
Already correct: 3
Errors: 0
Skipped (filtered out): 1,078
======================================================================
```

### Dry Run Output

```
...
Processing objects...

[1/10] 🔍 ...assets/images/logo.png (Would update (Current: none))
[2/10] 🔍 ...assets/images/banner.jpg (Would update (Current: public, max-age=3600))
...

======================================================================
DRY RUN Update Complete!
======================================================================
Total objects in bucket: 1,234
Objects processed: 10
Successful updates: 10
Already correct: 0
Errors: 0
Skipped (filtered out): 1,224
======================================================================

💡 This was a dry run. Remove --dry-run flag to make actual changes.
```

## Troubleshooting

### "Error: Access denied to bucket"

**Solution:**
1. Check AWS credentials: `aws sts get-caller-identity`
2. Verify IAM permissions (see above)
3. Check bucket policy allows your IAM user/role

### "Error: Bucket does not exist"

**Solution:**
1. Verify bucket name spelling
2. Check if bucket is in different region (use `--region` flag)
3. Ensure bucket isn't deleted

### "Rate limiting / Too many requests"

**Solution:**
- Reduce `--max-workers` to 5 or lower
- AWS S3 has request rate limits per prefix

### "Operation taking too long"

**Solution:**
- Use `--folder` to process specific directories
- Increase `--max-workers` for faster processing
- Process in batches using folder filters

### No objects match filters

**Solution:**
1. Verify folder names (check for trailing slashes)
2. Check file patterns (case-sensitive matching)
3. Try `--dry-run` first to see what's being filtered
4. Use `--no-extension-filter` if processing non-images

## Best Practices

1. **Always test with dry-run first:**
   ```bash
   python s3_cache_control_manager.py update --bucket my-bucket --dry-run
   ```

2. **Keep backups:**
   - Don't use `--no-backup` unless you're certain
   - Backup files are small (just metadata)

3. **Process in stages:**
   ```bash
   # Stage 1: Images folder
   python s3_cache_control_manager.py update --bucket my-bucket --folder assets/images/
   
   # Stage 2: Icons folder
   python s3_cache_control_manager.py update --bucket my-bucket --folder assets/icons/
   ```

4. **Use appropriate Cache-Control:**
   - Static assets with hashed names: `immutable, max-age=31536000`
   - Frequently changing assets: `max-age=3600` (1 hour)
   - Don't cache: `no-cache`

5. **Monitor CloudFront/CDN:**
   - If using CloudFront, invalidate cache after updates
   - Changes may take time to propagate

## Advanced Examples

### Update only specific image types

```bash
# Only PNG files in assets folder
python s3_cache_control_manager.py update \
  --bucket my-bucket \
  --folder assets/ \
  --file .png
```

### Update with custom metadata preservation

The script automatically preserves:
- Content-Type
- Content-Encoding
- Content-Language
- Content-Disposition
- All custom metadata

### Automation script example

```bash
#!/bin/bash
# update_s3_cache.sh

BUCKET="my-production-bucket"
FOLDERS=("assets/images/" "static/media/" "uploads/photos/")

for folder in "${FOLDERS[@]}"; do
    echo "Processing $folder..."
    python s3_cache_control_manager.py update \
        --bucket "$BUCKET" \
        --folder "$folder" \
        --yes \
        --max-workers 15
done

echo "All folders processed!"
```

## License

This script is provided as-is for managing S3 Cache-Control headers.

## Support

For issues or questions:
1. Check AWS CloudTrail logs for detailed error information
2. Verify IAM permissions
3. Test with dry-run mode first
4. Check backup files are being created correctly