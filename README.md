# GymForce - YN MK1

Internal Python/Tkinter keyboard workflow for Fitness First Calls and POSR entry.

## Requirements

- Windows 10 or Windows 11
- Python 3.10 or newer
- No third-party Python packages

## Install Python

Open PowerShell and run:

```powershell
winget install --id Python.Python.3.13 --exact --scope user
```

Accept the installation prompt, then close and reopen PowerShell. Confirm that
Python is ready:

```powershell
python --version
```

If `python` is not recognised but the Python launcher is available, use:

```powershell
py -3 --version
```

On a company-managed computer, WinGet or Python installation may require IT
approval. Do not bypass company security controls.

## Run

Open PowerShell in this folder:

```powershell
python .\GymForce_YN_MK1.py
```

If the Python launcher is used instead:

```powershell
py -3 .\GymForce_YN_MK1.py
```

## Calls

Select one of the five call outcomes, click **Run Calls**, then focus the
correct GymForce/Salesforce field during the countdown.

## POSR

Prepare a queue using:

```json
{
  "pending": [
    {
      "first_name": "Jane",
      "last_name": "Smith",
      "phone_number": "0412345678"
    }
  ],
  "completed": []
}
```

Click **Load Queue**, select the JSON file, click **Run POSR**, then focus the
correct GymForce/Salesforce field during the countdown.

## Text messages

Enter the person's first name under **C) Text Messages**, then click
**Text - Online Inquiry** (or press Enter). The personalised message is copied
to the Windows clipboard, ready to paste.

## Safety and data handling

- The app sends keystrokes to the window focused after the countdown.
- Test with non-sensitive sample data first.
- Calls do not consume the POSR queue.
- Do not commit real lead or customer information.
- Use only company-approved private repositories and storage locations.
