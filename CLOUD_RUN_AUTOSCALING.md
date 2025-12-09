# Cloud Run Autoscaling Configuration

This document describes the Cloud Run autoscaling configuration for NexMDM production deployments.

## Current Configuration

- **Min Instances**: 1 (always keep at least 1 instance running)
- **Max Instances**: 10 (scale up to 10 instances under load)
- **CPU**: 2 vCPU per instance
- **Memory**: 2GB per instance
- **Concurrency**: 80 requests per instance
- **Timeout**: 300 seconds (5 minutes)
- **CPU Throttling**: Enabled (allows Cloud Run to scale based on CPU usage)

## Autoscaling Behavior

Cloud Run will automatically scale based on:
- **CPU utilization**: Scales when CPU usage exceeds ~70% (default Cloud Run threshold)
- **Request rate**: Scales when request queue builds up
- **Concurrent requests**: Scales when approaching concurrency limit (80 per instance)

## Configuration Files

### For Replit Deployments

Replit uses Cloud Run for deployments. The autoscaling settings can be configured via:

1. **Replit UI**: Go to Deployments → Settings → Autoscaling
2. **Environment Variables**: Set via Replit Secrets
3. **Manual gcloud command** (if you have access):

```bash
gcloud run services update nexmdm \
  --min-instances=1 \
  --max-instances=10 \
  --cpu=2 \
  --memory=2Gi \
  --concurrency=80 \
  --timeout=300 \
  --cpu-throttling \
  --region=us-central1
```

### For Direct Cloud Run Deployments

Use the `service.yaml` file in this repository:

```bash
gcloud run services replace service.yaml --region=us-central1
```

## Monitoring

Monitor autoscaling behavior via:
- Cloud Run Metrics dashboard
- Request latency (p95, p99)
- Instance count over time
- CPU and memory utilization

## Troubleshooting

**Backend still crashing despite autoscaling:**
- Check if autoscaling is actually enabled (min/max instances set correctly)
- Verify CPU throttling is enabled
- Check database connection pool limits
- Review memory usage (may need to increase memory limit)

**Slow scaling:**
- Cloud Run typically scales within 10-30 seconds
- If slower, check for cold start issues
- Consider increasing min-instances if traffic is predictable

**Cost optimization:**
- Reduce min-instances to 0 if traffic is sporadic (adds cold start delay)
- Reduce max-instances if you don't need 10 instances
- Monitor actual usage and adjust accordingly

