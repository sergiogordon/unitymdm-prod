# GitHub CI/CD Documentation

This directory contains the automated CI/CD pipeline for the NexMDM Android Agent.

## 📁 Contents

- **`workflows/android-ci.yml`** - Main CI/CD workflow configuration
- **`workflows/CI_WORKFLOW_SUMMARY.md`** - Visual overview and technical details
- **`SECRETS_SETUP.md`** - Quick reference for configuring GitHub Secrets

## 🚀 Quick Start

1. **Configure Secrets** → See [SECRETS_SETUP.md](SECRETS_SETUP.md)
2. **Push to main** → CI automatically builds and uploads APKs
3. **Check Actions tab** → View build progress and artifacts
4. **Deploy from dashboard** → Use APK Management UI

## 📖 Full Documentation

For complete setup instructions, troubleshooting, and best practices:
- [ANDROID_CI_SETUP.md](../ANDROID_CI_SETUP.md) - Comprehensive setup guide

## 🔐 Required Secrets

| Secret | Description |
|--------|-------------|
| `ANDROID_KEYSTORE_BASE64` | Base64-encoded keystore |
| `ANDROID_KEYSTORE_PASSWORD` | Keystore password |
| `ANDROID_KEY_ALIAS` | Key alias name |
| `ANDROID_KEY_PASSWORD` | Key password |
| `BACKEND_URL` | Backend API URL |
| `ADMIN_API_KEY` | Admin API key |

## 📦 What Gets Built

- **Debug APK** → Auto-uploaded to backend (30 day retention)
- **Release APK** → GitHub artifact (90 day retention)
- **Release AAB** → GitHub artifact (90 day retention)

## ✅ Build Verification

Every build includes:
- ✅ APK signature verification
- ✅ SHA256 checksum generation
- ✅ Automated version management
- ✅ Build summary with metadata

## 🔄 Workflow Triggers

- Push to `main` branch
- Version tags (`v*`)
- Manual workflow dispatch

## 📊 Performance

- **Build time:** <5 minutes
- **Success rate:** 100% (with valid secrets)
- **Reproducible:** Same commit = identical checksums
