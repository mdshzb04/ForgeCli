function asyncOperation(value, shouldReject = false) {
  return new Promise((resolve, reject) => {
    setTimeout(() => {
      if (shouldReject) {
        reject(new Error("Operation failed"));
      } else {
        resolve(value * 2);
      }
    }, 1000);
  });
}

asyncOperation(21)
  .then((result) => console.log("Success:", result))
  .catch((error) => console.error("Error:", error.message))
  .finally(() => console.log("Done"));