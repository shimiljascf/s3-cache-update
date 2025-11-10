# S3 Cache-Control Manager - Quick Reference

## 🚀 Most Common Use Cases

### 1. Update All Images (Default Behavior)
```bash
python s3_cache_control_manager.py update --bucket my-bucket
```

### 2. Update Specific Folder
```bash
python s3_cache_control_manager.py update \
  --bucket my-bucket \
  --folder assets/images/
```

### 3. Update Multiple Folders
```bash
python s3_cache_control_manager.py update \
  --bucket my-bucket \
  --folder assets/images/ static/media/ icons/
```

### 4. Update Files by Name Pattern
```bash
python s3_cache_control_manager.py update \
  --bucket my-bucket \
  --file logo banner icon
```

### 5. Dry Run (Preview Changes)
```bash
python s3_cache_control_manager.py update \
  --bucket my-bucket \
  --folder assets/ \
  --dry-run
```

### 6. Revert Changes
```bash
python s3_cache_control_manager.py revert \
  --bucket my-bucket \
  --backup .s3_cache_backups/my-bucket_update_20250110_143052.json
```

## 📋 Command Line Options

### Update Command
| Option | Description | Example |
|--------|-------------|---------|
| `--bucket` | S3 bucket name (required) | `--bucket my-bucket` |
| `--cache-control` | Cache-Control header | `--cache-control "public, max-age=86400"` |
| `--folder` | Filter by folder prefix | `--folder assets/` |
| `--file` | Filter by filename pattern | `--file logo` |
| `--no-extension-filter` | Process all file types | `--no-extension-filter` |
| `--dry-run` | Preview without changes | `--dry-run` |
| `--yes` | Skip confirmation | `--yes` |
| `--max-workers` | Parallel workers (1-20) | `--max-workers 15` |
| `--region` | AWS region | `--region us-west-2` |
| `--no-backup` | Skip backup creation | `--no-backup` |

### Revert Command
| Option | Description | Example |
|--------|-------------|---------|
| `--bucket` | S3 bucket name (required) | `--bucket my-bucket` |
| `--backup` | Backup file path (required) | `--backup backup.json` |
| `--dry-run` | Preview without changes | `--dry-run` |
| `--yes` | Skip confirmation | `--yes` |
| `--max-workers` | Parallel workers | `--max-workers 10` |

## 🎯 Common Cache-Control Values

| Use Case | Cache-Control Value |
|----------|---------------------|
| Static assets with hashed names | `public, max-age=31536000, immutable` |
| Images updated daily | `public, max-age=86400` |
| Images updated hourly | `public, max-age=3600` |
| Dynamic content | `public, max-age=300` |
| Always revalidate | `no-cache` |
| Never cache | `private, max-age=0, no-cache` |

## 🔍 File Extensions

### Default Allowed (Images/SVGs)
- Images: `.jpg`, `.jpeg`, `.png`, `.gif`, `.webp`, `.bmp`, `.ico`, `.avif`, `.heic`, `.heif`
- Vectors: `.svg`
- Other: `.tiff`, `.tif`

### Default Skipped
- Web: `.html`, `.htm`, `.css`, `.js`
- Data: `.json`, `.xml`, `.txt`

To process ALL files: `--no-extension-filter`

## ⚡ Performance Tips

| Bucket Size | Recommended Workers | Reason |
|-------------|---------------------|---------|
| < 1,000 objects | 10 (default) | Good balance |
| 1,000 - 10,000 | 15-20 | Faster processing |
| > 10,000 | 10-15 | Avoid rate limits |

Adjust based on:
- Network speed
- AWS rate limits
- API throttling

## 🛡️ Safety Checklist

- [ ] Run with `--dry-run` first
- [ ] Check folder/file filters are correct
- [ ] Verify backup is created (check `.s3_cache_backups/`)
- [ ] Test revert with `--dry-run` on backup
- [ ] Keep backup files for recovery

## 📝 Workflow Example

```bash
# 1. Preview what would change
python s3_cache_control_manager.py update \
  --bucket production-assets \
  --folder assets/images/ \
  --dry-run

# 2. If looks good, run actual update
python s3_cache_control_manager.py update \
  --bucket production-assets \
  --folder assets/images/

# 3. If needed, revert using backup file
python s3_cache_control_manager.py revert \
  --bucket production-assets \
  --backup .s3_cache_backups/production-assets_update_20250110_143052.json
```

## 🔧 Troubleshooting

| Error | Solution |
|-------|----------|
| Access denied | Check IAM permissions (see README) |
| Bucket not found | Verify bucket name and region |
| Rate limiting | Reduce `--max-workers` |
| No objects match | Check folder/file patterns, try `--dry-run` |

## 📊 Output Interpretation

```
[1/156] ✓ assets/images/logo.png          # Successfully updated
[2/156] ⊘ assets/images/icon.svg (...)    # Skipped (already correct)
[3/156] 🔍 assets/images/banner.jpg (...)  # Dry run (would update)
[4/156] ✗ assets/images/missing.png       # Error
```

## 💡 Pro Tips

1. **Always dry-run first** - Prevents mistakes
2. **Use folder filters** - Faster than processing entire bucket
3. **Keep backups** - Easy recovery if needed
4. **Process in stages** - Break large updates into smaller batches
5. **Monitor CloudFront** - Invalidate CDN cache after updates

## 🔗 Related AWS Commands

```bash
# List all objects in bucket
aws s3 ls s3://my-bucket --recursive

# Check Cache-Control of specific file
aws s3api head-object --bucket my-bucket --key assets/logo.png

# Invalidate CloudFront cache
aws cloudfront create-invalidation \
  --distribution-id E123456789ABC \
  --paths "/assets/*"
```

## 📞 Support

Check the full README.md for:
- Detailed examples
- Logic verification
- IAM permission setup
- Advanced usage patterns
- Complete troubleshooting guide