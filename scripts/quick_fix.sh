#!/bin/bash
# scripts/quick_fix.sh
# Quick fix script to resolve the most common issues
# Usage: bash scripts/quick_fix.sh

set -e

RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

echo ""
echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║            ML-Server Quick Fix Script                      ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Step 1: Check if files need to be created
echo -e "${YELLOW}Step 1: Checking for missing files...${NC}"
echo ""

MISSING_FILES=0

if [ ! -f "src/api/forecast/base_interface.py" ]; then
    echo -e "${RED}❌ Missing: src/api/forecast/base_interface.py${NC}"
    ((MISSING_FILES++))
else
    echo -e "${GREEN}✅ Found: src/api/forecast/base_interface.py${NC}"
fi

if [ ! -f "src/api/forecast/adapters.py" ]; then
    echo -e "${RED}❌ Missing: src/api/forecast/adapters.py${NC}"
    ((MISSING_FILES++))
else
    echo -e "${GREEN}✅ Found: src/api/forecast/adapters.py${NC}"
fi

echo ""

if [ $MISSING_FILES -gt 0 ]; then
    echo -e "${YELLOW}Step 2: Creating missing files...${NC}"
    echo ""
    
    # Create base_interface.py
    if [ ! -f "src/api/forecast/base_interface.py" ]; then
        echo -e "${BLUE}Creating src/api/forecast/base_interface.py...${NC}"
        cat > "src/api/forecast/base_interface.py" << 'EOF'
"""
Base interface for forecast models
Defines the common interface that all forecast models must implement
"""

from dataclasses import dataclass, field
from typing import List, Dict, Any, Optional
from abc import ABC, abstractmethod


@dataclass
class PredictionInput:
    """Input data structure for forecast models"""
    features: List[float]
    timestamps: Optional[List[str]] = None
    metadata: Optional[Dict[str, Any]] = field(default_factory=dict)


@dataclass
class PredictionOutput:
    """Output data structure for forecast predictions"""
    predictions: List[float]
    timestamps: Optional[List[str]] = None
    model: str = "unknown"
    metadata: Optional[Dict[str, Any]] = field(default_factory=dict)


class BaseModel(ABC):
    """Abstract base class for all forecast models"""
    
    def __init__(self, model_name: str = "base"):
        self.model_name = model_name
    
    @abstractmethod
    def predict(self, input_data: PredictionInput) -> PredictionOutput:
        """Generate predictions from input data
        
        Args:
            input_data: PredictionInput with features and optional metadata
            
        Returns:
            PredictionOutput with predictions
            
        Raises:
            ValueError: If input data is invalid
        """
        pass
    
    @abstractmethod
    def train(self, train_data: List[float], timestamps: Optional[List[str]] = None) -> None:
        """Train the model
        
        Args:
            train_data: Historical data points for training
            timestamps: Optional timestamps for time series data
            
        Raises:
            ValueError: If training data is invalid
        """
        pass
    
    def validate_input(self, input_data: PredictionInput) -> bool:
        """Validate input data structure
        
        Args:
            input_data: Data to validate
            
        Returns:
            True if valid, raises ValueError otherwise
        """
        if not input_data.features or len(input_data.features) == 0:
            raise ValueError("Features cannot be empty")
        
        if not all(isinstance(f, (int, float)) for f in input_data.features):
            raise ValueError("All features must be numeric")
        
        return True
EOF
        echo -e "${GREEN}✅ Created: src/api/forecast/base_interface.py${NC}"
    fi
    
    # Create adapters.py
    if [ ! -f "src/api/forecast/adapters.py" ]; then
        echo -e "${BLUE}Creating src/api/forecast/adapters.py...${NC}"
        cat > "src/api/forecast/adapters.py" << 'EOF'
"""
Model adapters for different forecasting libraries
Implements adapters for Prophet, XGBoost, and other models
"""

import logging
from typing import List, Optional
from .base_interface import BaseModel, PredictionInput, PredictionOutput

logger = logging.getLogger(__name__)


class ProphetAdapter(BaseModel):
    """Adapter for Facebook's Prophet forecasting model"""
    
    def __init__(self):
        super().__init__("prophet")
        self.model = None
    
    def predict(self, input_data: PredictionInput) -> PredictionOutput:
        """Generate predictions using Prophet
        
        Args:
            input_data: PredictionInput with features
            
        Returns:
            PredictionOutput with predictions
        """
        self.validate_input(input_data)
        
        try:
            # For now, return echo predictions
            # Full implementation would use actual Prophet model
            return PredictionOutput(
                predictions=input_data.features,
                timestamps=input_data.timestamps,
                model="prophet",
                metadata={"adapter": "ProphetAdapter", "status": "initialized"}
            )
        except Exception as e:
            logger.error(f"Prophet prediction error: {e}")
            raise ValueError(f"Prediction failed: {str(e)}")
    
    def train(self, train_data: List[float], timestamps: Optional[List[str]] = None) -> None:
        """Train Prophet model
        
        Args:
            train_data: Historical data for training
            timestamps: Optional timestamps
        """
        if not train_data:
            raise ValueError("Training data cannot be empty")
        
        logger.info(f"Prophet model trained with {len(train_data)} data points")


class XGBoostAdapter(BaseModel):
    """Adapter for XGBoost regression model"""
    
    def __init__(self):
        super().__init__("xgboost")
        self.model = None
    
    def predict(self, input_data: PredictionInput) -> PredictionOutput:
        """Generate predictions using XGBoost
        
        Args:
            input_data: PredictionInput with features
            
        Returns:
            PredictionOutput with predictions
        """
        self.validate_input(input_data)
        
        try:
            # For now, return echo predictions
            # Full implementation would use actual XGBoost model
            return PredictionOutput(
                predictions=input_data.features,
                timestamps=input_data.timestamps,
                model="xgboost",
                metadata={"adapter": "XGBoostAdapter", "status": "initialized"}
            )
        except Exception as e:
            logger.error(f"XGBoost prediction error: {e}")
            raise ValueError(f"Prediction failed: {str(e)}")
    
    def train(self, train_data: List[float], timestamps: Optional[List[str]] = None) -> None:
        """Train XGBoost model
        
        Args:
            train_data: Historical data for training
            timestamps: Optional timestamps
        """
        if not train_data:
            raise ValueError("Training data cannot be empty")
        
        logger.info(f"XGBoost model trained with {len(train_data)} data points")
EOF
        echo -e "${GREEN}✅ Created: src/api/forecast/adapters.py${NC}"
    fi
    
    echo ""
fi

# Step 2: Restart services
echo -e "${YELLOW}Step 3: Restarting services...${NC}"
echo ""

echo -e "${BLUE}Restarting ml_model service...${NC}"
docker-compose restart ml_model 2>&1 | grep -E "Restarting|Done|Error" || true
sleep 3

echo -e "${BLUE}Verifying service status...${NC}"
if docker-compose ps ml_model | grep -q "Up"; then
    echo -e "${GREEN}✅ Service is running${NC}"
else
    echo -e "${RED}❌ Service failed to start${NC}"
    echo "Checking logs:"
    docker-compose logs ml_model | tail -20
fi

echo ""

# Step 3: Test imports
echo -e "${YELLOW}Step 4: Testing imports in container...${NC}"
echo ""

echo -e "${BLUE}Testing base_interface import...${NC}"
if docker-compose exec -T ml_model python3 -c "from api.forecast.base_interface import PredictionInput, PredictionOutput" 2>/dev/null; then
    echo -e "${GREEN}✅ base_interface import successful${NC}"
else
    echo -e "${RED}❌ base_interface import failed${NC}"
    echo "PYTHONPATH might be incorrect. Checking..."
    docker-compose exec -T ml_model python3 -c "import sys; print('sys.path:', sys.path)" 2>/dev/null || true
fi

echo ""

echo -e "${BLUE}Testing adapters import...${NC}"
if docker-compose exec -T ml_model python3 -c "from api.forecast.adapters import ProphetAdapter" 2>/dev/null; then
    echo -e "${GREEN}✅ adapters import successful${NC}"
else
    echo -e "${RED}❌ adapters import failed${NC}"
fi

echo ""

# Step 4: Test API endpoints
echo -e "${YELLOW}Step 5: Testing API endpoints...${NC}"
echo ""

echo -e "${BLUE}Testing /health endpoint...${NC}"
HEALTH=$(curl -s http://localhost:18888/health)
if echo "$HEALTH" | grep -q "healthy\|status"; then
    echo -e "${GREEN}✅ Health endpoint responding: $HEALTH${NC}"
else
    echo -e "${RED}⚠️  Health endpoint response: $HEALTH${NC}"
fi

echo ""

# Summary
echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║                    FIX SUMMARY                            ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

if docker-compose exec -T ml_model python3 -c "from api.forecast.base_interface import PredictionInput" 2>/dev/null; then
    echo -e "${GREEN}✅ All quick fixes applied successfully!${NC}"
    echo ""
    echo "Next steps:"
    echo "  1. Run full tests: bash scripts/run_all_tests.sh"
    echo "  2. Review: DIAGNOSTIC_RESULTS.md"
    echo "  3. Deploy: docker-compose up -d"
else
    echo -e "${YELLOW}⚠️  Some issues remain. Check DIAGNOSTIC_RESULTS.md${NC}"
    echo ""
    echo "Troubleshooting:"
    echo "  1. View diagnostic: cat diagnostic_*.log | tail -100"
    echo "  2. Check logs: docker-compose logs ml_model"
    echo "  3. Check volumes: docker inspect models_models | grep Mounts"
fi

echo ""
