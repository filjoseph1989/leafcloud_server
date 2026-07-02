[Prev](./page-48-manual-zeroconf-testing.md)

# Page 49 — Nutrient Classifier V11: Code Walkthrough

Line-by-line explanation of the top-level constants in `scripts/nutrient_classifier_v11.py`.

---

```python
BATCH_SIZE = 32
```

Number of training samples processed per gradient update during model training. TensorFlow feeds 32 image+sensor pairs through the network at a time, computes the loss, and updates the weights — then repeats for the next batch. Smaller batches use less GPU memory but produce noisier gradients; 32 is a common default that balances the two.

---

```python
TIMESTAMP = datetime.now().strftime('%Y%m%d_%H%M')
```

Captures the current date and time at the moment the script runs, formatted as e.g. `20260612_1430`. Used on the next line to name the output model file:

```python
MODEL_SAVE_PATH = f'leafcloud_multimodal_v11_{TIMESTAMP}.keras'
```

Each training run saves to a uniquely named file like `leafcloud_multimodal_v11_20260612_1430.keras`, preventing previous runs from being overwritten.

---

```python
SENSOR_NORM = {
    'ph':         (3.0, 10.0),
    'ec':         (0.0, 1.6),
    'water_temp': (24.0, 29.0),
}
```

Defines the min/max range for each sensor reading, used to normalize raw values to a 0–1 scale before feeding them into the model.

For example, a pH of 6.5 becomes `(6.5 - 3.0) / (10.0 - 3.0) ≈ 0.5`. This ensures all three sensor inputs are on the same scale so no single feature dominates training due to its unit magnitude.

---

```python
LABEL_LIST = ['Water', 'NPK', 'Micro', 'Mix']
```

Defines the four nutrient treatment classes the model classifies leaf images into:

- **Water** — plain water, no nutrients
- **NPK** — macro nutrients (Nitrogen, Phosphorus, Potassium)
- **Micro** — micronutrients
- **Mix** — combination of the above

---

```python
LABEL_TO_IDX = {l: i for i, l in enumerate(LABEL_LIST)}
```

A **dict comprehension** that converts `LABEL_LIST` into a label-to-integer mapping.

- `enumerate(LABEL_LIST)` produces pairs: `(0, 'Water'), (1, 'NPK'), (2, 'Micro'), (3, 'Mix')`
- `for i, l in ...` unpacks each pair into index `i` and label `l`
- `l: i` makes the label the key and the index the value

Result: `{'Water': 0, 'NPK': 1, 'Micro': 2, 'Mix': 3}` — used during training to convert string labels into integers the model can process.

---

```python
engine = create_engine(DB_URL)
```

Creates a SQLAlchemy database connection engine — the entry point for all database operations in the script. It does not open a connection immediately; it sets up the configuration so that when `fetch_raw_data(engine)` is called, SQLAlchemy knows how and where to connect (PostgreSQL host, port, credentials, database name) to run the SQL queries that pull training data.

---

```python
df = pd.read_sql(query, engine)
```

Executes the SQL query against the database and loads the results directly into a Pandas DataFrame. Each row in `df` becomes one training sample — containing the image file path, the three sensor readings (pH, EC, water temp), and the bucket label (Water/NPK/Micro/Mix). The rest of the script then uses this DataFrame to load images, normalize sensor values, and feed everything into model training.

---

```python
if df.empty:
    return df
```

An early exit guard inside `filter_missing_images()`. If the DataFrame has no rows (e.g. the database returned nothing), there is nothing to verify, so the function returns immediately rather than proceeding with file-existence checks on an empty dataset. Prevents unnecessary work and avoids errors that would occur if later code assumed at least one row existed.

---

```python
print('🔍 Verifying image files on disk...')
def is_accessible(path):
    try:
        with open(path, 'rb') as f:
            f.read(1)
        return True
    except:
        return False
```

Defines a helper function that checks whether an image file actually exists and is readable on disk. It tries to open the file in binary mode and read one byte — if that succeeds, the file is accessible and returns `True`; if anything goes wrong (file missing, permission error, corrupted path), it catches the exception and returns `False`. This is used to filter out rows pointing to missing images before training starts, so the model never hits a file-not-found error mid-epoch.

---

```python
tqdm.pandas(desc='Checking files')
```

Patches Pandas with a progress bar from the `tqdm` library. After this call, `.progress_apply()` can be used instead of `.apply()` on a DataFrame column — it behaves identically but displays a live progress bar labeled `Checking files` in the terminal so you can see how many image paths have been verified so far.

---

```python
df['exists'] = df['image_path'].progress_apply(is_accessible)
```

Runs the `is_accessible` function on every row's `image_path` and stores the result (`True` or `False`) in a new column called `exists`. After this line, each row knows whether its image file is actually on disk. The progress bar from `tqdm.pandas()` shows live progress as it checks each file.

---

```python
missing = (~df['exists']).sum()
if missing:
    print(f'⚠️  {missing} inaccessible files removed.')
```

Counts how many rows have `exists = False` by inverting the column with `~` and summing the `True` values. If any missing files were found, prints a warning with the count. This gives immediate visibility into how many training samples will be dropped before the DataFrame is filtered down to only accessible images.

---

```python
return df[df['exists']].drop(columns=['exists']).reset_index(drop=True)
```

Three operations chained together on one line:

- `df[df['exists']]` — keeps only rows where `exists` is `True`, discarding any with missing image files
- `.drop(columns=['exists'])` — removes the temporary `exists` column since it was only needed for filtering and isn't part of the training data
- `.reset_index(drop=True)` — resets row numbers to 0, 1, 2, … so the index is clean and contiguous after rows were dropped

Returns the filtered, cleaned DataFrame ready for training.

---

```python
df['timestamp'] = pd.to_datetime(df['timestamp'])
```

Converts the `timestamp` column from a raw string (e.g. `"2026-05-01 08:30:00"`) into a proper Pandas `datetime` object. This allows the column to be used for time-based operations like sorting, grouping by date, or train/test splitting by time period — none of which work correctly on plain strings.

---

```python
for exp_id, group in df.groupby('experiment_id'):
```

Iterates over the DataFrame split by `experiment_id` — each iteration gives one experiment's rows as a separate sub-DataFrame (`group`). Inside the loop, it finds the earliest and latest timestamp for that experiment and stores them in `exp_time_bounds`. This is used to calculate how far along (in time) each reading falls within its experiment — needed for computing continuous time-based depletion targets.

**Example:** say `df` looks like this:

| image_path | experiment_id | timestamp |
|---|---|---|
| crop1.jpg | 1 | 2026-05-01 |
| crop2.jpg | 1 | 2026-05-05 |
| crop3.jpg | 2 | 2026-05-10 |
| crop4.jpg | 2 | 2026-05-15 |

`groupby('experiment_id')` splits it into two groups:

- **exp_id = 1** → rows for crop1 and crop2 → `min_ts = 2026-05-01`, `max_ts = 2026-05-05`
- **exp_id = 2** → rows for crop3 and crop4 → `min_ts = 2026-05-10`, `max_ts = 2026-05-15`

Result stored in `exp_time_bounds`:
```python
{
    1: (2026-05-01, 2026-05-05),
    2: (2026-05-10, 2026-05-15),
}
```

Later, each reading's timestamp is compared against its experiment's min/max to compute how far into the depletion cycle it falls (0.0 = start, 1.0 = end).

[Prev](./page-48-manual-zeroconf-testing.md)