> "Act as a Lead Developer for the LEAFCLOUD project. Our pH hardware is currently failing (stuck at 1.13V), so we are pivoting to a **Hybrid Data Strategy** to ensure we finish the capstone on time for graduation.
> **Your Task:** Update the project files to support simulated pH data while maintaining the real-time pipeline for EC and Temperature.
> **Specific Instructions:**
> 1. **Database Update:** Modify the `sensor_data` table schema to add a boolean column named `ph_is_estimated`. Default this to `True` for now .
> 2. **Leaf Node Logic:** Update `leaf_node.py` to use a hardcoded pH value of **6.0** (the ideal range for lettuce) instead of the raw ADC reading from A1 .
> 3. **API Integration:** Update the FastAPI endpoint to accept this new `ph_is_estimated` flag so it is stored correctly in the cloud database.
> 4. **Recommendation System:** Ensure the logic in the app or backend still calculates NPK Estimation based on the 'composite variable' definition, using the simulated 6.0 pH as a temporary baseline .
> 5. **Documentation Support:** Add comments in the code explaining that this is a temporary software fix due to hardware bottlenecks, ensuring research transparency for the defense ."
