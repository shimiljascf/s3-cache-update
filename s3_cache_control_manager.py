#!/usr/bin/env python3
"""
Enhanced S3 Cache-Control Management Script
============================================
Features:
- Update cache-control headers for objects by folder/file patterns
- Revert changes using backup metadata
- Dry-run mode for testing
- Parallel processing for large buckets
- Comprehensive error handling and logging
"""

import boto3
from botocore.exceptions import ClientError, BotoCoreError
import sys
import os
import json
import argparse
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Dict, Tuple, Optional
import re

# ==============================================================================
# CONFIGURATION
# ==============================================================================

# Default cache-control settings
DEFAULT_CACHE_CONTROL = 'public, max-age=31536000, immutable'
DEFAULT_MAX_WORKERS = 10

# File extensions to update (images and SVGs by default)
DEFAULT_ALLOWED_EXTENSIONS = {
    '.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.ico',
    '.svg', '.tiff', '.tif', '.avif', '.heic', '.heif'
}

# Skip specific extensions (HTML, CSS, JS)
DEFAULT_SKIP_EXTENSIONS = {'.html', '.htm', '.css', '.js', '.json', '.xml', '.txt'}

# Backup file location
BACKUP_DIR = '.s3_cache_backups'
os.makedirs(BACKUP_DIR, exist_ok=True)

# ==============================================================================
# HELPER FUNCTIONS
# ==============================================================================

def get_backup_filename(bucket: str, operation: str) -> str:
    """Generate a timestamped backup filename."""
    timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
    return os.path.join(BACKUP_DIR, f'{bucket}_{operation}_{timestamp}.json')


def save_backup(backup_data: List[Dict], filename: str) -> None:
    """Save backup data to a JSON file."""
    try:
        with open(filename, 'w') as f:
            json.dump(backup_data, f, indent=2)
        print(f"✓ Backup saved to: {filename}")
    except Exception as e:
        print(f"⚠️  Warning: Could not save backup file: {e}")


def load_backup(filename: str) -> List[Dict]:
    """Load backup data from a JSON file."""
    try:
        with open(filename, 'r') as f:
            return json.load(f)
    except FileNotFoundError:
        print(f"❌ Error: Backup file not found: {filename}")
        sys.exit(1)
    except json.JSONDecodeError:
        print(f"❌ Error: Invalid backup file format: {filename}")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error loading backup file: {e}")
        sys.exit(1)


def matches_pattern(key: str, patterns: List[str], match_type: str = 'prefix') -> bool:
    """
    Check if a key matches any of the given patterns.
    
    Args:
        key: S3 object key
        patterns: List of patterns to match against
        match_type: 'prefix', 'suffix', 'contains', or 'regex'
    
    Returns:
        True if key matches any pattern
    """
    if not patterns:
        return True  # No filter means match all
    
    for pattern in patterns:
        if match_type == 'prefix':
            if key.startswith(pattern):
                return True
        elif match_type == 'suffix':
            if key.endswith(pattern):
                return True
        elif match_type == 'contains':
            if pattern in key:
                return True
        elif match_type == 'regex':
            try:
                if re.search(pattern, key):
                    return True
            except re.error:
                print(f"⚠️  Warning: Invalid regex pattern: {pattern}")
    
    return False


def should_process_file(
    key: str,
    folder_filters: List[str],
    file_filters: List[str],
    allowed_extensions: set,
    skip_extensions: set,
    use_extension_filter: bool = True
) -> Tuple[bool, str]:
    """
    Check if file should be processed based on filters and extensions.
    
    Args:
        key: S3 object key (file path)
        folder_filters: List of folder prefixes to include
        file_filters: List of filename patterns to include
        allowed_extensions: Set of allowed file extensions
        skip_extensions: Set of extensions to skip
        use_extension_filter: Whether to apply extension filtering
    
    Returns:
        Tuple of (should_process: bool, reason: str)
    """
    # Handle empty keys
    if not key or key.strip() == '':
        return False, "Empty key"
    
    # Skip S3 "folders" (keys ending with /)
    if key.endswith('/'):
        return False, "Directory marker"
    
    # Apply folder filters
    if folder_filters:
        if not matches_pattern(key, folder_filters, 'prefix'):
            return False, "Does not match folder filter"
    
    # Apply file filters
    if file_filters:
        filename = key.split('/')[-1]
        if not matches_pattern(filename, file_filters, 'contains'):
            return False, "Does not match file filter"
    
    # Apply extension filters if enabled
    if use_extension_filter:
        # Get file extension
        if '.' not in key.lower():
            return False, "No extension"
        
        extension = '.' + key.lower().split('.')[-1]
        
        # Check skip list first
        if extension in skip_extensions:
            return False, f"Skipped extension: {extension}"
        
        # Check allowed list
        if extension not in allowed_extensions:
            return False, f"Extension not in allowed list: {extension}"
    
    return True, "Matches filters"


def verify_aws_credentials(s3_client, bucket: str) -> bool:
    """
    Verify AWS credentials and bucket access.
    
    Returns:
        True if credentials are valid and bucket is accessible
    """
    try:
        s3_client.head_bucket(Bucket=bucket)
        return True
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', 'Unknown')
        if error_code == '404':
            print(f"❌ Error: Bucket '{bucket}' does not exist")
        elif error_code == '403':
            print(f"❌ Error: Access denied to bucket '{bucket}'")
            print("   Check your AWS credentials and IAM permissions")
        else:
            print(f"❌ Error accessing bucket: {error_code}")
        return False
    except Exception as e:
        print(f"❌ Error verifying credentials: {e}")
        return False


def list_all_objects(s3_client, bucket: str, prefix: str = '') -> List[str]:
    """
    List all objects in an S3 bucket with optional prefix.
    
    Args:
        s3_client: Boto3 S3 client
        bucket: S3 bucket name
        prefix: Optional prefix to filter objects
    
    Returns:
        List of object keys
    """
    objects = []
    paginator = s3_client.get_paginator('list_objects_v2')
    
    try:
        page_count = 0
        pagination_config = {'Bucket': bucket}
        if prefix:
            pagination_config['Prefix'] = prefix
        
        for page in paginator.paginate(**pagination_config):
            page_count += 1
            if 'Contents' in page:
                for obj in page['Contents']:
                    objects.append(obj['Key'])
            
            # Progress indicator for large buckets
            if page_count % 10 == 0:
                print(f"  ... fetched {len(objects)} objects so far")
        
        return objects
    
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', 'Unknown')
        if error_code == 'NoSuchBucket':
            print(f"❌ Error: Bucket '{bucket}' does not exist")
        elif error_code == 'AccessDenied':
            print(f"❌ Error: Access denied to bucket '{bucket}'")
            print("   Check your AWS credentials and permissions")
        else:
            print(f"❌ Error listing objects: {error_code} - {e}")
        sys.exit(1)
    
    except Exception as e:
        print(f"❌ Unexpected error listing objects: {e}")
        sys.exit(1)


def update_object_metadata(
    s3_client,
    bucket: str,
    key: str,
    cache_control: str,
    dry_run: bool = False,
    save_backup: bool = True
) -> Dict:
    """
    Update cache-control metadata for a single S3 object.
    
    Args:
        s3_client: Boto3 S3 client
        bucket: S3 bucket name
        key: S3 object key
        cache_control: Cache-Control header value
        dry_run: If True, don't actually make changes
        save_backup: If True, include original metadata in return
    
    Returns:
        Dictionary with status, key, backup data, and optional error/info
    """
    try:
        # Get current object metadata
        try:
            response = s3_client.head_object(Bucket=bucket, Key=key)
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            if error_code == '404':
                return {'status': 'error', 'key': key, 'error': 'Object not found (404)'}
            elif error_code == '403':
                return {'status': 'error', 'key': key, 'error': 'Access denied (403)'}
            else:
                return {'status': 'error', 'key': key, 'error': f'Head object failed: {error_code}'}
        
        # Store backup data
        backup_data = None
        if save_backup:
            backup_data = {
                'key': key,
                'cache_control': response.get('CacheControl', ''),
                'content_type': response.get('ContentType', ''),
                'metadata': response.get('Metadata', {}),
                'content_encoding': response.get('ContentEncoding'),
                'content_language': response.get('ContentLanguage'),
                'content_disposition': response.get('ContentDisposition'),
            }
        
        # Check if Cache-Control is already set correctly
        current_cache_control = response.get('CacheControl', '')
        if current_cache_control == cache_control:
            return {
                'status': 'skipped',
                'key': key,
                'info': 'Already has correct Cache-Control',
                'backup': backup_data
            }
        
        if dry_run:
            return {
                'status': 'dry_run',
                'key': key,
                'info': f'Would update (Current: {current_cache_control or "none"})',
                'backup': backup_data
            }
        
        # Prepare metadata for copy
        metadata = response.get('Metadata', {})
        content_type = response.get('ContentType', 'binary/octet-stream')
        
        # Build copy arguments
        copy_source = {'Bucket': bucket, 'Key': key}
        copy_args = {
            'Bucket': bucket,
            'Key': key,
            'CopySource': copy_source,
            'MetadataDirective': 'REPLACE',
            'CacheControl': cache_control,
            'ContentType': content_type,
            'Metadata': metadata
        }
        
        # Add optional attributes if they exist
        for attr, arg_name in [
            ('ContentEncoding', 'ContentEncoding'),
            ('ContentLanguage', 'ContentLanguage'),
            ('ContentDisposition', 'ContentDisposition')
        ]:
            value = response.get(attr)
            if value:
                copy_args[arg_name] = value
        
        # Perform the copy
        s3_client.copy_object(**copy_args)
        
        return {'status': 'success', 'key': key, 'backup': backup_data}
    
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', 'Unknown')
        error_msg = e.response.get('Error', {}).get('Message', str(e))
        return {'status': 'error', 'key': key, 'error': f'{error_code}: {error_msg}'}
    
    except BotoCoreError as e:
        return {'status': 'error', 'key': key, 'error': f'AWS Error: {str(e)}'}
    
    except Exception as e:
        return {'status': 'error', 'key': key, 'error': f'Unexpected error: {str(e)}'}


def revert_object_metadata(s3_client, bucket: str, backup_item: Dict, dry_run: bool = False) -> Dict:
    """
    Revert an object's metadata from backup data.
    
    Args:
        s3_client: Boto3 S3 client
        bucket: S3 bucket name
        backup_item: Backup data dictionary
        dry_run: If True, don't actually make changes
    
    Returns:
        Dictionary with status, key, and optional error/info
    """
    key = backup_item['key']
    
    try:
        # Verify object still exists
        try:
            s3_client.head_object(Bucket=bucket, Key=key)
        except ClientError as e:
            error_code = e.response.get('Error', {}).get('Code', 'Unknown')
            if error_code == '404':
                return {'status': 'error', 'key': key, 'error': 'Object not found (may have been deleted)'}
            else:
                return {'status': 'error', 'key': key, 'error': f'Cannot access object: {error_code}'}
        
        if dry_run:
            return {
                'status': 'dry_run',
                'key': key,
                'info': f'Would revert (Cache-Control: {backup_item.get("cache_control") or "none"})'
            }
        
        # Build copy arguments from backup
        copy_source = {'Bucket': bucket, 'Key': key}
        copy_args = {
            'Bucket': bucket,
            'Key': key,
            'CopySource': copy_source,
            'MetadataDirective': 'REPLACE',
            'ContentType': backup_item.get('content_type', 'binary/octet-stream'),
            'Metadata': backup_item.get('metadata', {})
        }
        
        # Add cache-control if it was set originally
        if backup_item.get('cache_control'):
            copy_args['CacheControl'] = backup_item['cache_control']
        
        # Add optional attributes from backup
        for key_name, arg_name in [
            ('content_encoding', 'ContentEncoding'),
            ('content_language', 'ContentLanguage'),
            ('content_disposition', 'ContentDisposition')
        ]:
            value = backup_item.get(key_name)
            if value:
                copy_args[arg_name] = value
        
        # Perform the copy
        s3_client.copy_object(**copy_args)
        
        return {'status': 'success', 'key': key}
    
    except ClientError as e:
        error_code = e.response.get('Error', {}).get('Code', 'Unknown')
        error_msg = e.response.get('Error', {}).get('Message', str(e))
        return {'status': 'error', 'key': key, 'error': f'{error_code}: {error_msg}'}
    
    except Exception as e:
        return {'status': 'error', 'key': key, 'error': f'Unexpected error: {str(e)}'}


# ==============================================================================
# MAIN OPERATIONS
# ==============================================================================

def operation_update(args):
    """Main function to update cache-control for objects in bucket."""
    
    print("="*70)
    print("S3 Cache-Control Update Operation")
    print("="*70)
    
    # Initialize S3 client
    try:
        if args.region:
            s3_client = boto3.client('s3', region_name=args.region)
        else:
            s3_client = boto3.client('s3')
    except Exception as e:
        print(f"\n❌ Error initializing AWS client: {e}")
        print("   Make sure AWS credentials are configured (aws configure)")
        sys.exit(1)
    
    # Display configuration
    print(f"\nBucket: {args.bucket}")
    print(f"Cache-Control: {args.cache_control}")
    print(f"Dry Run Mode: {'ENABLED (no changes will be made)' if args.dry_run else 'DISABLED'}")
    print(f"Max Workers: {args.max_workers}")
    
    if args.folders:
        print(f"Folder Filters: {', '.join(args.folders)}")
    if args.files:
        print(f"File Filters: {', '.join(args.files)}")
    if not args.no_extension_filter:
        print(f"Extension Filter: ENABLED (images/SVGs only)")
    else:
        print(f"Extension Filter: DISABLED (all files)")
    
    # Verify credentials and bucket access
    print("\nVerifying AWS credentials and bucket access...")
    if not verify_aws_credentials(s3_client, args.bucket):
        sys.exit(1)
    print("✓ Credentials verified")
    
    # List all objects
    print("\nListing all objects in bucket...")
    prefix = args.folders[0] if args.folders and len(args.folders) == 1 else ''
    object_keys = list_all_objects(s3_client, args.bucket, prefix)
    total_objects = len(object_keys)
    
    if total_objects == 0:
        print("No objects found in bucket.")
        return
    
    print(f"✓ Found {total_objects} objects")
    
    # Filter objects based on criteria
    print("\nFiltering objects...")
    filtered_keys = []
    skip_reasons = {}
    
    allowed_ext = DEFAULT_ALLOWED_EXTENSIONS if not args.no_extension_filter else set()
    skip_ext = DEFAULT_SKIP_EXTENSIONS if not args.no_extension_filter else set()
    
    for key in object_keys:
        should_process, reason = should_process_file(
            key,
            args.folders,
            args.files,
            allowed_ext,
            skip_ext,
            not args.no_extension_filter
        )
        if should_process:
            filtered_keys.append(key)
        else:
            skip_reasons[reason] = skip_reasons.get(reason, 0) + 1
    
    skipped_count = total_objects - len(filtered_keys)
    
    print(f"\n✓ Objects to update: {len(filtered_keys)}")
    print(f"✓ Objects skipped: {skipped_count}")
    
    if skip_reasons:
        print("\nSkip reasons:")
        for reason, count in sorted(skip_reasons.items(), key=lambda x: x[1], reverse=True):
            print(f"  - {reason}: {count}")
    
    if len(filtered_keys) == 0:
        print("\n⚠️  No matching objects found to update.")
        return
    
    # Confirmation prompt
    if not args.dry_run and not args.yes:
        print(f"\n⚠️  About to update Cache-Control for {len(filtered_keys)} objects.")
        response = input("Continue? (yes/no): ")
        if response.lower() not in ['yes', 'y']:
            print("Operation cancelled.")
            return
    
    print("\nProcessing objects...\n")
    
    # Update objects in parallel
    success_count = 0
    error_count = 0
    skipped_count_existing = 0
    backup_data = []
    
    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        # Submit all tasks
        future_to_key = {
            executor.submit(
                update_object_metadata,
                s3_client,
                args.bucket,
                key,
                args.cache_control,
                args.dry_run,
                not args.no_backup
            ): key
            for key in filtered_keys
        }
        
        # Process completed tasks
        for i, future in enumerate(as_completed(future_to_key), 1):
            result = future.result()
            
            # Store backup data
            if result.get('backup') and not args.no_backup:
                backup_data.append(result['backup'])
            
            # Display progress
            key_display = result['key']
            if len(key_display) > 60:
                key_display = '...' + key_display[-57:]
            
            if result['status'] == 'success':
                success_count += 1
                print(f"[{i}/{len(filtered_keys)}] ✓ {key_display}")
            elif result['status'] == 'skipped':
                skipped_count_existing += 1
                print(f"[{i}/{len(filtered_keys)}] ⊘ {key_display} ({result.get('info', 'skipped')})")
            elif result['status'] == 'dry_run':
                success_count += 1
                print(f"[{i}/{len(filtered_keys)}] 🔍 {key_display} ({result.get('info', 'would update')})")
            else:
                error_count += 1
                print(f"[{i}/{len(filtered_keys)}] ✗ {key_display}")
                print(f"    Error: {result.get('error', 'Unknown error')}")
    
    # Save backup if not dry run and backup is enabled
    if not args.dry_run and backup_data and not args.no_backup:
        backup_file = get_backup_filename(args.bucket, 'update')
        save_backup(backup_data, backup_file)
        print(f"\n💾 To revert these changes, run:")
        print(f"   python {sys.argv[0]} revert --bucket {args.bucket} --backup {backup_file}")
    
    # Summary
    print(f"\n{'='*70}")
    print(f"{'DRY RUN ' if args.dry_run else ''}Update Complete!")
    print(f"{'='*70}")
    print(f"Total objects in bucket: {total_objects}")
    print(f"Objects processed: {len(filtered_keys)}")
    print(f"Successful updates: {success_count}")
    print(f"Already correct: {skipped_count_existing}")
    print(f"Errors: {error_count}")
    print(f"Skipped (filtered out): {skipped_count}")
    print(f"{'='*70}")
    
    if args.dry_run:
        print("\n💡 This was a dry run. Remove --dry-run flag to make actual changes.")
    
    if error_count > 0:
        print(f"\n⚠️  {error_count} errors occurred. Check the output above for details.")
        sys.exit(1)


def operation_revert(args):
    """Revert cache-control changes using backup file."""
    
    print("="*70)
    print("S3 Cache-Control Revert Operation")
    print("="*70)
    
    # Load backup file
    print(f"\nLoading backup file: {args.backup}")
    backup_data = load_backup(args.backup)
    print(f"✓ Loaded {len(backup_data)} objects from backup")
    
    # Initialize S3 client
    try:
        if args.region:
            s3_client = boto3.client('s3', region_name=args.region)
        else:
            s3_client = boto3.client('s3')
    except Exception as e:
        print(f"\n❌ Error initializing AWS client: {e}")
        sys.exit(1)
    
    print(f"\nBucket: {args.bucket}")
    print(f"Dry Run Mode: {'ENABLED (no changes will be made)' if args.dry_run else 'DISABLED'}")
    print(f"Max Workers: {args.max_workers}")
    
    # Verify credentials
    print("\nVerifying AWS credentials and bucket access...")
    if not verify_aws_credentials(s3_client, args.bucket):
        sys.exit(1)
    print("✓ Credentials verified")
    
    # Confirmation prompt
    if not args.dry_run and not args.yes:
        print(f"\n⚠️  About to revert {len(backup_data)} objects to their previous state.")
        response = input("Continue? (yes/no): ")
        if response.lower() not in ['yes', 'y']:
            print("Operation cancelled.")
            return
    
    print("\nReverting objects...\n")
    
    # Revert objects in parallel
    success_count = 0
    error_count = 0
    
    with ThreadPoolExecutor(max_workers=args.max_workers) as executor:
        # Submit all tasks
        future_to_key = {
            executor.submit(revert_object_metadata, s3_client, args.bucket, item, args.dry_run): item['key']
            for item in backup_data
        }
        
        # Process completed tasks
        for i, future in enumerate(as_completed(future_to_key), 1):
            result = future.result()
            
            key_display = result['key']
            if len(key_display) > 60:
                key_display = '...' + key_display[-57:]
            
            if result['status'] == 'success':
                success_count += 1
                print(f"[{i}/{len(backup_data)}] ✓ {key_display}")
            elif result['status'] == 'dry_run':
                success_count += 1
                print(f"[{i}/{len(backup_data)}] 🔍 {key_display} ({result.get('info', 'would revert')})")
            else:
                error_count += 1
                print(f"[{i}/{len(backup_data)}] ✗ {key_display}")
                print(f"    Error: {result.get('error', 'Unknown error')}")
    
    # Summary
    print(f"\n{'='*70}")
    print(f"{'DRY RUN ' if args.dry_run else ''}Revert Complete!")
    print(f"{'='*70}")
    print(f"Objects processed: {len(backup_data)}")
    print(f"Successfully reverted: {success_count}")
    print(f"Errors: {error_count}")
    print(f"{'='*70}")
    
    if args.dry_run:
        print("\n💡 This was a dry run. Remove --dry-run flag to make actual changes.")
    
    if error_count > 0:
        print(f"\n⚠️  {error_count} errors occurred. Check the output above for details.")
        sys.exit(1)


# ==============================================================================
# CLI INTERFACE
# ==============================================================================

def main():
    """Main CLI entry point."""
    parser = argparse.ArgumentParser(
        description='S3 Cache-Control Management Tool',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Update all images in bucket
  python s3_cache_control_manager.py update --bucket my-bucket
  
  # Update only images in 'assets/images/' folder
  python s3_cache_control_manager.py update --bucket my-bucket --folder assets/images/
  
  # Update files matching pattern in filename
  python s3_cache_control_manager.py update --bucket my-bucket --file logo
  
  # Update specific folders and files
  python s3_cache_control_manager.py update --bucket my-bucket --folder assets/ icons/ --file banner
  
  # Update all files (disable extension filter)
  python s3_cache_control_manager.py update --bucket my-bucket --no-extension-filter
  
  # Dry run to see what would be changed
  python s3_cache_control_manager.py update --bucket my-bucket --dry-run
  
  # Revert changes from backup
  python s3_cache_control_manager.py revert --bucket my-bucket --backup .s3_cache_backups/backup.json
        """
    )
    
    subparsers = parser.add_subparsers(dest='operation', help='Operation to perform')
    
    # Update command
    update_parser = subparsers.add_parser('update', help='Update cache-control headers')
    update_parser.add_argument('--bucket', required=True, help='S3 bucket name')
    update_parser.add_argument(
        '--cache-control',
        default=DEFAULT_CACHE_CONTROL,
        help=f'Cache-Control header value (default: {DEFAULT_CACHE_CONTROL})'
    )
    update_parser.add_argument(
        '--folder',
        '--folders',
        dest='folders',
        nargs='+',
        help='Filter by folder prefix(es), e.g., assets/images/ icons/'
    )
    update_parser.add_argument(
        '--file',
        '--files',
        dest='files',
        nargs='+',
        help='Filter by filename pattern(s), e.g., logo banner'
    )
    update_parser.add_argument(
        '--no-extension-filter',
        action='store_true',
        help='Disable extension filtering (process all files)'
    )
    update_parser.add_argument(
        '--region',
        help='AWS region (optional, uses default if not specified)'
    )
    update_parser.add_argument(
        '--max-workers',
        type=int,
        default=DEFAULT_MAX_WORKERS,
        help=f'Number of parallel workers (default: {DEFAULT_MAX_WORKERS})'
    )
    update_parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview changes without making them'
    )
    update_parser.add_argument(
        '--no-backup',
        action='store_true',
        help='Skip creating backup file'
    )
    update_parser.add_argument(
        '-y', '--yes',
        action='store_true',
        help='Skip confirmation prompt'
    )
    
    # Revert command
    revert_parser = subparsers.add_parser('revert', help='Revert changes from backup')
    revert_parser.add_argument('--bucket', required=True, help='S3 bucket name')
    revert_parser.add_argument('--backup', required=True, help='Backup file path')
    revert_parser.add_argument(
        '--region',
        help='AWS region (optional, uses default if not specified)'
    )
    revert_parser.add_argument(
        '--max-workers',
        type=int,
        default=DEFAULT_MAX_WORKERS,
        help=f'Number of parallel workers (default: {DEFAULT_MAX_WORKERS})'
    )
    revert_parser.add_argument(
        '--dry-run',
        action='store_true',
        help='Preview changes without making them'
    )
    revert_parser.add_argument(
        '-y', '--yes',
        action='store_true',
        help='Skip confirmation prompt'
    )
    
    args = parser.parse_args()
    
    if not args.operation:
        parser.print_help()
        sys.exit(1)
    
    # Execute operation
    if args.operation == 'update':
        operation_update(args)
    elif args.operation == 'revert':
        operation_revert(args)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        print("\n\n⚠️  Operation cancelled by user")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n❌ Unexpected error: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)