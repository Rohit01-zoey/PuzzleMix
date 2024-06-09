import random
import sys

# Randomly raise an exception
if random.choice([True, False]):
    raise Exception("Random exception")
else:
    print("Success!")
    sys.exit(0)