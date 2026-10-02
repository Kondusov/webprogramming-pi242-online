#!/usr/bin/env python3
"""
Локальный запуск мессенджера.
    python run.py
"""
from server.main import main
import asyncio

if __name__ == "__main__":
    asyncio.run(main())