#!/usr/bin/env python3
"""
Compatibilidad legacy.
Este archivo se mantiene para no romper flujos antiguos,
pero delega toda la operación al sistema único.
"""

from sistema_hibrido import main


if __name__ == "__main__":
    main()
