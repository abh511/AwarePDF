#!/bin/bash
# Setup script for AwarePDF

set -e

echo "🚀 Setting up AwarePDF..."

# Check Python version
if ! command -v python3 &> /dev/null; then
    echo "❌ Python 3 is not installed. Please install Python 3.8 or higher."
    exit 1
fi

PYTHON_VERSION=$(python3 --version | cut -d' ' -f2 | cut -d'.' -f1,2)
echo "✅ Found Python $PYTHON_VERSION"

# Create virtual environment
if [ ! -d ".venv" ]; then
    echo "📦 Creating virtual environment..."
    python3 -m venv .venv
else
    echo "✅ Virtual environment already exists"
fi

# Activate virtual environment
echo "🔧 Activating virtual environment..."
source .venv/bin/activate

# Upgrade pip
echo "⬆️  Upgrading pip..."
pip install --upgrade pip --quiet

# Install dependencies
echo "📥 Installing dependencies (this may take a few minutes)..."
pip install -r requirements.txt --quiet

# Create .env if it doesn't exist
if [ ! -f ".env" ]; then
    echo "📝 Creating .env file from template..."
    cp .env.example .env
    echo "⚠️  Please edit .env and add your API keys:"
    echo "   - GROQ_API_KEY (required) - Get from https://console.groq.com"
    echo "   - GOOGLE_API_KEY (optional) - For better summaries"
else
    echo "✅ .env file already exists"
fi

# Create data directories
echo "📁 Creating data directories..."
mkdir -p data/chroma_db data/uploads data/processed

echo ""
echo "✅ Setup complete!"
echo ""
echo "Next steps:"
echo "1. Edit .env and add your GROQ_API_KEY"
echo "2. Run: source .venv/bin/activate"
echo "3. Run: python run.py"
echo ""
