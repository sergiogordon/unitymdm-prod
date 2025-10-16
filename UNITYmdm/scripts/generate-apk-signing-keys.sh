#!/bin/bash

# APK Signing Keys Generator for NexMDM
# This script generates a keystore for signing your Android APK

set -e

echo "🔐 NexMDM APK Signing Keys Generator"
echo "===================================="
echo ""
echo "This script will generate a keystore for signing your Android APK."
echo "You'll need these values as GitHub Secrets for automated builds."
echo ""

# Create temp directory for keystore
TEMP_DIR=$(mktemp -d)
KEYSTORE_PATH="$TEMP_DIR/nexmdm-release.jks"

# Prompt for keystore password
echo -n "Enter keystore password (min 6 characters): "
read -s KEYSTORE_PASSWORD
echo ""

if [ ${#KEYSTORE_PASSWORD} -lt 6 ]; then
    echo "❌ Error: Password must be at least 6 characters long"
    rm -rf "$TEMP_DIR"
    exit 1
fi

# Prompt for key alias
echo -n "Enter key alias [default: nexmdm]: "
read KEY_ALIAS
KEY_ALIAS=${KEY_ALIAS:-nexmdm}

# Prompt for key password
echo -n "Enter key password (can be same as keystore password): "
read -s KEY_PASSWORD
echo ""

if [ ${#KEY_PASSWORD} -lt 6 ]; then
    echo "❌ Error: Key password must be at least 6 characters long"
    rm -rf "$TEMP_DIR"
    exit 1
fi

# Optional: Prompt for distinguished name fields
echo ""
echo "Optional: Enter your details for the certificate (press Enter to skip)"
echo -n "Your name or organization: "
read DNAME_CN
DNAME_CN=${DNAME_CN:-NexMDM User}

echo -n "Organizational unit (e.g., IT Department): "
read DNAME_OU
DNAME_OU=${DNAME_OU:-Mobile}

echo -n "Organization: "
read DNAME_O
DNAME_O=${DNAME_O:-NexMDM}

echo -n "City: "
read DNAME_L
DNAME_L=${DNAME_L:-Unknown}

echo -n "State: "
read DNAME_ST
DNAME_ST=${DNAME_ST:-Unknown}

echo -n "Country (2-letter code, e.g., US): "
read DNAME_C
DNAME_C=${DNAME_C:-US}

# Generate keystore
echo ""
echo "🔨 Generating keystore..."

DNAME="CN=$DNAME_CN, OU=$DNAME_OU, O=$DNAME_O, L=$DNAME_L, ST=$DNAME_ST, C=$DNAME_C"

keytool -genkeypair \
    -v \
    -keystore "$KEYSTORE_PATH" \
    -alias "$KEY_ALIAS" \
    -keyalg RSA \
    -keysize 2048 \
    -validity 10000 \
    -storepass "$KEYSTORE_PASSWORD" \
    -keypass "$KEY_PASSWORD" \
    -dname "$DNAME" \
    >/dev/null 2>&1

if [ $? -ne 0 ]; then
    echo "❌ Error: Failed to generate keystore"
    echo "Make sure you have Java/keytool installed"
    rm -rf "$TEMP_DIR"
    exit 1
fi

# Encode keystore to base64
echo "🔄 Encoding keystore to base64..."
KEYSTORE_BASE64=$(base64 -w 0 "$KEYSTORE_PATH" 2>/dev/null || base64 "$KEYSTORE_PATH" | tr -d '\n')

# Display results
echo ""
echo "✅ Keystore generated successfully!"
echo ""
echo "=========================================="
echo "COPY THESE VALUES TO GITHUB SECRETS"
echo "=========================================="
echo ""
echo "Go to: GitHub Repository → Settings → Secrets and variables → Actions"
echo "Add each of these as a 'New repository secret':"
echo ""
echo "Secret Name: KEYSTORE_BASE64"
echo "Value:"
echo "$KEYSTORE_BASE64"
echo ""
echo "Secret Name: KEYSTORE_PASSWORD"
echo "Value: $KEYSTORE_PASSWORD"
echo ""
echo "Secret Name: KEY_ALIAS"
echo "Value: $KEY_ALIAS"
echo ""
echo "Secret Name: KEY_PASSWORD"
echo "Value: $KEY_PASSWORD"
echo ""
echo "=========================================="
echo ""
echo "⚠️  IMPORTANT:"
echo "   - Save these values in a secure password manager"
echo "   - You'll need them to update your app in the future"
echo "   - Keep the KEYSTORE_BASE64 value secure - it's your signing key!"
echo ""
echo "📖 Next steps:"
echo "   1. Add these secrets to your GitHub repository"
echo "   2. Also add: NEXMDM_API_URL (your Replit URL)"
echo "   3. Also add: ADMIN_KEY (same as your backend ADMIN_KEY)"
echo "   4. Push a change to trigger the GitHub Actions build"
echo ""

# Cleanup
rm -rf "$TEMP_DIR"

echo "🎉 Done! Your APK signing keys are ready for GitHub Actions."
echo ""
