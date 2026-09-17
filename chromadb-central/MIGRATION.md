# PostgreSQL Migration Guide

Complete guide for migrating from ChromaDB to Azure PostgreSQL + pgvector.

## Overview

This migration transforms the NutriFAQ API from using ChromaDB (file-based vector store) to Azure PostgreSQL with pgvector extension. Benefits:

- ✅ Centralized database management
- ✅ Better scalability and performance
- ✅ Native vector similarity search
- ✅ Automatic failover and backups
- ✅ Monitoring and analytics

## Prerequisites

1. **Azure PostgreSQL Flexible Server** set up with:
   - Host: `nutrifaq-bd-server.postgres.database.azure.com`
   - Port: `5432`
   - Database: `postgres` or custom DB name
   - User: your admin username
   - Password: your admin password

2. **pgvector extension installed** (automatically created on first use)

3. **Environment Variables** set:
   ```powershell
   $env:POSTGRES_HOST = "nutrifaq-bd-server.postgres.database.azure.com"
   $env:POSTGRES_PORT = "5432"
   $env:POSTGRES_DB = "postgres"
   $env:POSTGRES_USER = "your_username"
   $env:POSTGRES_PASSWORD = "your_password"
   $env:POSTGRES_SSLMODE = "require"
   ```

## Quick Start

### 1. Test Migration Setup

Run tests to verify PostgreSQL connectivity and ChromaDB project discovery:

```powershell
cd chromadb-central
.\migrate-to-postgres.ps1 -Test
```

**Expected output:**
```
✅ PostgreSQL Connection
✅ ChromaDB Discovery
✅ Migration Status
✅ Table Creation
✅ Route Import
```

### 2. Check Current Status

See what's currently in PostgreSQL and what's available in ChromaDB:

```powershell
.\migrate-to-postgres.ps1 -Status
```

**Output includes:**
- Number of tables in PostgreSQL
- Documents per table
- Available ChromaDB projects and collections

### 3. Migrate Single Collection

Migrate one specific collection to test the process:

```powershell
.\migrate-to-postgres.ps1 -Project nutria -Collection gdrive_documents
```

### 4. Full Migration

Migrate all ChromaDB projects and collections:

```powershell
.\migrate-to-postgres.ps1 -Migrate
```

## API Endpoints

Once migration is complete, use these endpoints to manage migrations:

### Check Migration Status
```bash
GET /migration/status
```
Returns current PostgreSQL tables and document counts.

### List Available Projects
```bash
GET /migration/projects
```
Shows all ChromaDB projects and their collections.

### Migrate All Data
```bash
POST /migration/migrate-all
```
Starts background migration of all ChromaDB data to PostgreSQL.

### Migrate Single Collection
```bash
POST /migration/migrate/{project_name}/{collection_name}
```
Example: `POST /migration/migrate/nutria/gdrive_documents`

### Migration Health
```bash
GET /migration/health
```
Returns PostgreSQL connection status and document count.

## Database Schema

The migration creates tables with the following schema:

```sql
CREATE TABLE "{project}_{collection}" (
    id SERIAL PRIMARY KEY,
    uuid TEXT UNIQUE,
    content TEXT NOT NULL,
    embedding vector(3072),          -- OpenAI text-embedding-3-large
    metadata JSONB,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);

-- Indexes for performance
CREATE INDEX idx_{project}_{collection}_embedding 
    ON "{project}_{collection}" 
    USING ivfflat (embedding vector_cosine_ops) 
    WITH (lists = 100);

CREATE INDEX idx_{project}_{collection}_uuid 
    ON "{project}_{collection}" (uuid);

CREATE INDEX idx_{project}_{collection}_content 
    ON "{project}_{collection}" 
    USING GIN (to_tsvector('english', content));
```

## Batch Processing

The migration uses batch processing for efficiency:

- **Batch Size**: 100 documents per database transaction
- **Memory Usage**: Optimized for large datasets
- **Resume Support**: Failed batches can be retried (ON CONFLICT DO UPDATE)

## Monitoring Progress

### Via API
```bash
curl https://nutrifaq-chat.azurewebsites.net/migration/status
```

### Via Python
```python
from api.migrate_to_postgres import get_migration_status
status = get_migration_status()
print(f"Total documents: {status['total_documents']}")
```

## Troubleshooting

### Connection Error: "No PostgreSQL connection available"

**Cause**: Environment variables not set or PostgreSQL not accessible
**Solution**:
1. Verify Azure PostgreSQL server is running
2. Check firewall rules allow your PC/App Service IP
3. Verify connection string:
   ```powershell
   $env:POSTGRES_HOST
   $env:POSTGRES_USER
   $env:POSTGRES_PASSWORD
   ```

### Error: "No pgvector table found"

**Cause**: Table hasn't been created yet
**Solution**: Run migration for that collection first
```powershell
.\migrate-to-postgres.ps1 -Project nutria -Collection gdrive_documents
```

### Error: "failed to resolve host"

**Cause**: Local PC cannot reach private PostgreSQL server
**Solution**: Set up Azure VPN Gateway Point-to-Site VPN or use public endpoint with firewall rules

### Migration is slow

**Cause**: Large dataset or slow network connection
**Solution**: 
1. Increase batch size in `migrate_collection_data()` (default: 100)
2. Check network connection quality
3. Verify Azure SQL server has enough compute resources

## Automatic Fallback

The API includes automatic fallback logic:

```python
if postgres_configured:
    try:
        results = query_pgvector(project, collection, query)
    except Exception:
        # Fall back to ChromaDB
        results = chroma_query(project, collection, query)
else:
    # Use ChromaDB
    results = chroma_query(project, collection, query)
```

This means the API continues working during migration.

## Production Deployment

1. **Test locally** with `-Test` flag
2. **Verify network access** to PostgreSQL
3. **Perform test migration** on one small collection
4. **Monitor production** with `/migration/health` endpoint
5. **Gradually migrate** collections one by one
6. **Switch routes** after verifying PostgreSQL results match ChromaDB

## Performance Tuning

### Vector Similarity Search
The default IVFFlat index provides good performance for:
- Exact nearest neighbor search: O(log n)
- Approximate search: O(k) where k = nlist (default 100)

### Query Optimization
```python
# Fast: Indexes are used
SELECT * FROM table ORDER BY embedding <-> query_vector LIMIT 10

# Slow: Full table scan
SELECT * WHERE content ILIKE '%keyword%'
```

## Rollback Plan

If migration fails or causes issues:

1. **Keep ChromaDB collections** (they're preserved during migration)
2. **Remove environment variables** to revert to ChromaDB-only mode
3. **Redeploy** the application
4. **Investigate** errors from `/migration/status` endpoint

## Next Steps

1. Set PostgreSQL environment variables
2. Run `.\migrate-to-postgres.ps1 -Test`
3. Run `.\migrate-to-postgres.ps1 -Migrate`
4. Monitor with `GET /migration/status`
5. Switch API to use PostgreSQL by default (update query.py)

## Support

For issues or questions:
1. Check test output with `.\migrate-to-postgres.ps1 -Test`
2. Review migration status: `.\migrate-to-postgres.ps1 -Status`
3. Check Azure PostgreSQL server logs
4. Verify network connectivity to PostgreSQL server
