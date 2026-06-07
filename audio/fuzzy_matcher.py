"""
Fuzzy Match Score Generator
Reads Excel file with transcriptions and computes fuzzy match scores.
"""

import argparse
import os
import pandas as pd
from difflib import SequenceMatcher


def fuzzy_match_ratio(str_a, str_b):
    """Compute fuzzy match ratio between two strings (0.0 to 1.0)."""
    # Handle NaN and non-string types
    str_a = str(str_a) if str_a is not None else ""
    str_b = str(str_b) if str_b is not None else ""
    
    # Skip if empty
    if not str_a or not str_b:
        return 0.0
    
    return SequenceMatcher(None, str_a.lower(), str_b.lower()).ratio()


def compute_fuzzy_scores(excel_file, reference_text=None, output_file=None, inplace=True):
    """
    Read Excel file with transcriptions and compute fuzzy match scores.
    
    Args:
        excel_file: Path to Excel file with 'File Name' and 'Extracted Text' columns
        reference_text: Reference text to compare against. If None, uses first row text
        output_file: Path to save output Excel. If None and inplace=True, overwrites input file
        inplace: If True, overwrites the input file (default). If False, saves to new file
    
    Returns:
        DataFrame with added 'Fuzzy Match Score' column
    """
    if not os.path.exists(excel_file):
        raise FileNotFoundError(f"Excel file not found: {excel_file}")
    
    # Read Excel
    df = pd.read_excel(excel_file)
    
    if "Extracted Text" not in df.columns:
        raise ValueError("Excel file must have 'Extracted Text' column")
    
    # Convert "Extracted Text" to string type and handle NaN
    df["Extracted Text"] = df["Extracted Text"].fillna("").astype(str)
    
    # Set reference text
    if reference_text is None:
        reference_text = df.iloc[0]["Extracted Text"]
        print(f"Using first row as reference:")
        print(f"  '{reference_text[:60]}...'")
    else:
        print(f"Using provided reference:")
        print(f"  '{reference_text[:60]}...'")
    
    # Compute fuzzy scores
    print(f"\nComputing fuzzy match scores for {len(df)} rows...")
    df["Fuzzy Match Score"] = df["Extracted Text"].apply(
        lambda text: fuzzy_match_ratio(reference_text, text)
    )
    
    # Round to 4 decimals
    df["Fuzzy Match Score"] = df["Fuzzy Match Score"].round(4)
    
    # Determine output file
    if output_file is None:
        if inplace:
            output_file = excel_file
            save_message = f"Updated original file: {output_file}"
        else:
            base, ext = os.path.splitext(excel_file)
            output_file = f"{base}_fuzzy.xlsx"
            save_message = f"Saved to new file: {output_file}"
    else:
        save_message = f"Saved to: {output_file}"
    
    # Save results
    df.to_excel(output_file, index=False)
    
    # Print statistics
    print(f"\n{'='*60}")
    print(f"Fuzzy Match Results")
    print(f"{'='*60}")
    print(f"Total rows: {len(df)}")
    print(f"Average score: {df['Fuzzy Match Score'].mean():.4f}")
    print(f"Median score: {df['Fuzzy Match Score'].median():.4f}")
    print(f"Min score: {df['Fuzzy Match Score'].min():.4f}")
    print(f"Max score: {df['Fuzzy Match Score'].max():.4f}")
    print(f"Std Dev: {df['Fuzzy Match Score'].std():.4f}")
    print(f"\n{save_message}")
    print(f"{'='*60}\n")
    
    return df


def main():
    parser = argparse.ArgumentParser(
        description="Compute fuzzy match scores for Excel transcriptions"
    )
    parser.add_argument(
        "excel_file",
        nargs="?",
        default="transcriptions_clean.xlsx",
        help="Excel file with 'Extracted Text' column (default: transcriptions_clean.xlsx)"
    )
    parser.add_argument(
        "--reference",
        default=None,
        help="Reference text to compare against (default: uses first row)"
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Output Excel file (default: updates input file in place)"
    )
    parser.add_argument(
        "--no-inplace",
        action="store_true",
        help="Create new file instead of updating input file (requires --output or uses _fuzzy suffix)"
    )
    
    args = parser.parse_args()
    
    try:
        inplace = not args.no_inplace
        
        df = compute_fuzzy_scores(
            args.excel_file,
            reference_text=args.reference,
            output_file=args.output,
            inplace=inplace
        )
        
        # Show sample results
        print("Sample results (sorted by score):")
        if "File Name" in df.columns:
            print(df[["File Name", "Fuzzy Match Score"]].sort_values(
                "Fuzzy Match Score", ascending=False
            ).head(5).to_string(index=False))
        else:
            print(df[["Extracted Text", "Fuzzy Match Score"]].sort_values(
                "Fuzzy Match Score", ascending=False
            ).head(5).to_string(index=False))
        print()
        
    except Exception as e:
        print(f"Error: {e}")
        return 1
    
    return 0


if __name__ == "__main__":
    exit(main())
