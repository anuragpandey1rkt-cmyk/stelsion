import os
import csv
import sys

def display_leaderboard():
    csv_file = "experiments/leaderboard.csv"
    if not os.path.exists(csv_file):
        print(f"Leaderboard file '{csv_file}' does not exist yet. Run a benchmark first!")
        sys.exit(0)
        
    entries = []
    with open(csv_file, mode="r", newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for row in reader:
            entries.append(row)
            
    if not entries:
        print("Leaderboard is empty. Run a benchmark to log results!")
        sys.exit(0)
        
    # Sort entries by F1 Score desc, Precision desc, False Positive Rate asc
    # We parse values to float for comparison, falling back to 0.0 or 1.0 safely
    def sort_key(row):
        try:
            f1 = float(row.get("F1 Score", 0.0))
        except ValueError:
            f1 = 0.0
        try:
            prec = float(row.get("Precision", 0.0))
        except ValueError:
            prec = 0.0
        try:
            fpr = float(row.get("False Positive Rate", 1.0))
        except ValueError:
            fpr = 1.0
        return (-f1, -prec, fpr)
        
    entries.sort(key=sort_key)
    
    # Print the leaderboard table
    print("\n" + "=" * 125)
    print("                     STELSION SHARED RESEARCH BENCHMARK LEADERBOARD")
    print("=" * 125)
    print(f"{'Rank':<5} | {'Model':<25} | {'Developer':<15} | {'Date':<19} | {'F1 Score':<8} | {'Precision':<9} | {'Recall':<8} | {'FPR':<6} | {'Inf Time (ms)':<13}")
    print("-" * 125)
    
    for idx, row in enumerate(entries, 1):
        model = row.get("Model", "N/A")
        dev = row.get("Developer", "N/A")
        date_str = row.get("Date", "N/A")
        if len(date_str) > 19:
            date_str = date_str[:19]
            
        f1 = row.get("F1 Score", "0.0")
        prec = row.get("Precision", "0.0")
        rec = row.get("Recall", "0.0")
        fpr = row.get("False Positive Rate", "0.0")
        inf_time = row.get("Inference Time (ms/sample)", "0.0")
        
        # Clip model/developer strings if too long
        if len(model) > 25:
            model = model[:22] + "..."
        if len(dev) > 15:
            dev = dev[:12] + "..."
            
        print(f"{idx:<5} | {model:<25} | {dev:<15} | {date_str:<19} | {f1:<8} | {prec:<9} | {rec:<8} | {fpr:<6} | {inf_time:<13}")
    print("=" * 125 + "\n")

if __name__ == "__main__":
    display_leaderboard()
