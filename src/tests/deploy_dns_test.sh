#!/bin/bash

PROJECT_ID="orchestrai-hackathon"
REGION="europe-west1"
JOB_NAME="dns-test-job"

echo "🐳 Pushing image to GCR..."
docker tag curlimages/curl gcr.io/$PROJECT_ID/$JOB_NAME
docker push gcr.io/$PROJECT_ID/$JOB_NAME

echo "🧹 Cleanup existing job (ignore if not exist)..."
gcloud beta run jobs delete $JOB_NAME --region=$REGION --quiet || true

echo "📄 Applying job definition..."
gcloud beta run jobs create $JOB_NAME \
  --region=$REGION \
  --image=gcr.io/$PROJECT_ID/$JOB_NAME \
  --vpc-connector=my-vpc-connector \
  --vpc-egress=all-traffic \
  --command="curl" \
  --args="-v,http://dev-agent.internal.orchestrai.ai/.well-known/agent.json"

echo "🚀 Executing job..."
gcloud beta run jobs execute $JOB_NAME --region=$REGION
