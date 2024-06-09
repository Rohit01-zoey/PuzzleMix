counter=0
while [ $counter -lt 3 ]; do
    python test_sh.py && break
    counter=$((counter+1))
    echo "Attempt $counter failed. Retrying..."
    sleep 1
done

if [ $counter -eq 3 ]; then
    echo "Command failed after 3 attempts."
fi