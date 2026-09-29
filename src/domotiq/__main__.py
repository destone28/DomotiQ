# SPDX-FileCopyrightText: 2026 Emilio Destratis – destratis.it
# SPDX-License-Identifier: MIT
from .app import main

# the guard matters: the vision process is started with "spawn", which imports the main module again
if __name__ == "__main__":
    main()
