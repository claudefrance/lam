# LAM: Linear Arithmetic Synthesis Bank Mutator 

## Overview
LAM (Linear Arithmetic Synthesis Bank Mutator) is a specialized software tool designed for sound designers and synthesizer enthusiasts. It allows users to manipulate and mutate Roland D-50 synthesizer SysEx (System Exclusive) data banks. By applying various algorithmic transformations to patch parameters, users can generate fresh, unexpected sound variations based on their existing library.

## Features
- **SysEx Support**: Loads and processes standard Roland D-50/D-550 `.syx` bank files.
- **Mutation Algorithms**:
    - **Standard**: Gaussian distribution-based variation.
    - **Drift**: Subtle, continuous shifting of values.
    - **Mirror**: Inverts the values of parameters.
    - **Chaos**: Randomizes parameters within the valid range (0-127).
- **Parameter Locks**: Protect specific sections of the patch architecture from being mutated to preserve core sonic characteristics:
    - Structures, Pitch, TVA, TVF, LFO, EQ, Bend/Portamento/Chase, and FX.
- **Intelligent Naming**: Automatically generates 80s-themed patch names using predefined lists of prefixes, nouns, and suffixes.
- **Visual Interface**:
    - Intuitive rotary knobs for mutation amount control.
    - Real-time LCD-style feedback for configuration settings.
    - System log console to track processing activity.
- **Batch Processing**: Generates multiple mutated banks in a single operation.

## Installation & Requirements
- **Language**: Python 3.x
- **Libraries**: `tkinter` (Standard GUI toolkit)
- **Execution**: Run the `main` script using `python lam.py`.

## User Interface Guide

### 1. File Import
- Click the **"LOAD SYSEX BANK"** button.
- Select a `.syx` file from your local storage.
- The status bar and LCD panel will reflect the loaded file name and size.

### 2. Configuration
- **Algorithm Selection**: Choose the desired mutation behavior from the dropdown menu.
- **Mutation Amount**: Use the rotary knob to adjust the intensity of the mutation (0% to 100%). Higher values result in more drastic sonic changes.
- **Parameter Locks**: Enable checkboxes to "freeze" specific parameter groups (e.g., LFO, TVF). This is essential for maintaining a consistent "character" while randomizing others.
- **Auto-Naming**: Enable/disable automatic 80s-style patch renaming.

### 3. Generation
- Set the desired number of output banks using the "Number of Banks" spinbox.
- Set the "Export Prefix Name" for the generated files.
- Click **"GENERATE BANKS"** and select a destination directory.
- The system log will display progress updates once the process is complete.

## Technical Details
- **Data Handling**: The application parses the raw binary SysEx structure, identifying Roland D-50 patch data (starting from `0x8000`).
- **Checksum Calculation**: Automatically recalculates the Roland-standard checksum for each mutated patch, ensuring the resulting `.syx` files are valid and loadable by hardware or software editors.
- **Encoding**: Uses a specific character mapping table (`D50_CHARSET`) to ensure that generated names conform to the D-50's internal byte-encoding requirements.

## Troubleshooting
- **File Format**: Ensure the file being loaded is a valid Roland D-50 SysEx file. The application requires F0...F7 SysEx message headers.
- **No Changes**: If the mutation is not audible, check if too many parameters are "Locked" or if the mutation rate is set too low.

