# Render Deployment Guide

This guide explains how to deploy the Solar Billing and PPA API to Render.

## Prerequisites

1. A Render account
2. Firebase project with Firestore enabled
3. Firebase service account key

## Step 1: Prepare Firebase Credentials

1. Go to your Firebase Console
2. Navigate to Project Settings > Service Accounts
3. Click "Generate new private key"
4. Download the JSON file
5. Copy the entire JSON content (you'll need this for the environment variable)

## Step 2: Create Render Web Service

1. Log in to Render Dashboard
2. Click "New +" and select "Web Service"
3. Connect your GitHub repository
4. Configure the service:

### Basic Settings
- **Name**: `solar-billing-api` (or your preferred name)
- **Environment**: `Python 3`
- **Region**: Choose closest to your users
- **Branch**: `main` (or your default branch)
- **Root Directory**: Leave empty (if code is in root)

### Build Settings
- **Build Command**: `pip install -r requirements.txt`
- **Start Command**: `uvicorn main:app --host 0.0.0.0 --port $PORT`

## Step 3: Configure Environment Variables

Add the following environment variables in Render:

### Required Variables
```
FIREBASE_CREDENTIALS_JSON={"type":"service_account","project_id":"your-project-id",...}
```

**Important**: The `FIREBASE_CREDENTIALS_JSON` should contain the entire JSON content from your Firebase service account key file.

### Optional Variables
```
FIREBASE_PROJECT_ID=your-project-id
```

## Step 4: Deploy

1. Click "Create Web Service"
2. Render will automatically build and deploy your application
3. Monitor the build logs for any issues

## Step 5: Verify Deployment

1. Check the health endpoint: `https://your-app-name.onrender.com/health`
2. Expected response:
```json
{
    "status": "healthy",
    "firebase_available": true,
    "timestamp": "2024-03-15T10:00:00Z"
}
```

## Environment Variable Setup

### In Render Dashboard:
1. Go to your web service
2. Click "Environment" tab
3. Add the `FIREBASE_CREDENTIALS_JSON` variable
4. Paste the entire JSON content from your Firebase service account key

### Example JSON Structure:
```json
{
    "type": "service_account",
    "project_id": "your-project-id",
    "private_key_id": "abc123...",
    "private_key": "-----BEGIN PRIVATE KEY-----\n...\n-----END PRIVATE KEY-----\n",
    "client_email": "firebase-adminsdk-xxxxx@your-project-id.iam.gserviceaccount.com",
    "client_id": "123456789",
    "auth_uri": "https://accounts.google.com/o/oauth2/auth",
    "token_uri": "https://oauth2.googleapis.com/token",
    "auth_provider_x509_cert_url": "https://www.googleapis.com/oauth2/v1/certs",
    "client_x509_cert_url": "https://www.googleapis.com/robot/v1/metadata/x509/firebase-adminsdk-xxxxx%40your-project-id.iam.gserviceaccount.com"
}
```

## Troubleshooting

### Common Issues:

1. **Firebase initialization fails**
   - Check that `FIREBASE_CREDENTIALS_JSON` is set correctly
   - Verify the JSON is valid and complete
   - Check build logs for specific error messages

2. **Build fails**
   - Ensure `requirements.txt` is in the root directory
   - Check that all dependencies are listed
   - Verify Python version compatibility

3. **Service unavailable errors**
   - Check the health endpoint: `/health`
   - Review application logs in Render dashboard
   - Verify Firebase project settings

### Debugging Steps:

1. **Check Health Endpoint**:
   ```bash
   curl https://your-app-name.onrender.com/health
   ```

2. **Review Logs**:
   - Go to your Render service
   - Click "Logs" tab
   - Look for error messages

3. **Test Firebase Connection**:
   - Check if `firebase_available` is `true` in health response
   - Review Firebase initialization messages in logs

## Security Best Practices

1. **Never commit credentials to Git**
   - Keep `firebase-credentials.json` in `.gitignore`
   - Use environment variables for all sensitive data

2. **Rotate credentials regularly**
   - Generate new Firebase service account keys periodically
   - Update environment variables in Render

3. **Monitor access**
   - Review Firebase Console for unusual activity
   - Set up alerts for authentication failures

## API Endpoints After Deployment

Your API will be available at:
- **Base URL**: `https://your-app-name.onrender.com`
- **Health Check**: `https://your-app-name.onrender.com/health`
- **API Documentation**: `https://your-app-name.onrender.com/docs`

## Environment Variables Reference

| Variable | Required | Description |
|----------|----------|-------------|
| `FIREBASE_CREDENTIALS_JSON` | Yes | Complete Firebase service account JSON |
| `FIREBASE_PROJECT_ID` | No | Firebase project ID (for reference) |

## Support

If you encounter issues:
1. Check the troubleshooting section above
2. Review Render documentation
3. Check Firebase Console for project status
4. Review application logs in Render dashboard 