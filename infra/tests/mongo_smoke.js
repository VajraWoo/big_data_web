// Only this fixed environment-check document is changed. No real review data.
const target = db.getSiblingDB("environment_checks");
const id = "week1-environment-persistence";
if (db.adminCommand({ping: 1}).ok !== 1) throw new Error("MongoDB ping failed");
if (process.env.CHECK_MODE === "write") {
  target.checks.replaceOne({_id: id}, {_id: id, purpose: "environment-only", value: 42}, {upsert: true});
}
const record = target.checks.findOne({_id: id});
if (!record || record.value !== 42 || record.purpose !== "environment-only") {
  throw new Error("MongoDB read/persistence check failed");
}
print(JSON.stringify({status: "PASS", version: db.version(), mode: process.env.CHECK_MODE || "read", id: record._id}));
