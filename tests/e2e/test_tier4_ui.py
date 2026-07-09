import os
import subprocess
import pytest
from pathlib import Path

def test_frontend_dashboard_build():
    """Verify that the Vite/React frontend dashboard builds without compilation errors (Tier 4)."""
    frontend_dir = Path("/Users/aditya/Downloads/SentinelOps/frontend")
    
    # Run npm run build in frontend folder
    print("Building frontend dashboard to check for errors...")
    res = subprocess.run(
        ["npm", "run", "build"],
        cwd=str(frontend_dir),
        capture_output=True,
        text=True
    )
    
    assert res.returncode == 0, f"Frontend build failed:\nStdout: {res.stdout}\nStderr: {res.stderr}"

def test_frontend_responsive_and_robustness_classes():
    """Verify frontend code contains responsive design layout and empty states (Tier 4)."""
    frontend_dir = Path("/Users/aditya/Downloads/SentinelOps/frontend")
    feed_file = frontend_dir / "src/components/IncidentFeed.tsx"
    app_file = frontend_dir / "src/App.tsx"
    
    assert feed_file.exists()
    assert app_file.exists()
    
    feed_content = feed_file.read_text()
    app_content = app_file.read_text()
    
    # Verify responsive design properties are present in the CSS/HTML classes
    # Check for Tailwind classes like grid, flex, sm:, md:, lg:, min-h
    assert any(cls in feed_content or cls in app_content for cls in ["flex", "grid", "sm:", "md:", "lg:"])
    
    # Verify handling of empty feed state
    assert "No active incidents" in feed_content
    
    # Verify API URL endpoints exist in the App
    assert "/api/incidents" in app_content or "api/incidents" in feed_content
