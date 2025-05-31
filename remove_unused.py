import os
import csv

def remove_unlabeled_images(all_chars_dir="all_chars", label_csv="char_labels.csv"):
    # 1. Read all labeled filenames from CSV
    labeled = set()
    with open(label_csv, newline='') as f:
        reader = csv.reader(f)
        for row in reader:
            if row:  # skip empty lines
                labeled.add(row[0])

    # 2. List all files in the directory
    all_files = set(f for f in os.listdir(all_chars_dir) if f.endswith(".png"))

    # 3. Find files not in the CSV
    to_remove = all_files - labeled

    # 4. Remove them
    for fname in to_remove:
        path = os.path.join(all_chars_dir, fname)
        print(f"Removing: {path}")
        os.remove(path)

    print(f"Removed {len(to_remove)} files.")

remove_unlabeled_images()
