---
name: db-query
description: Use this skill for any database checking, reporting, or data related tasks
---

Instructions for the skill go here. Provide relative paths to other resources in the skill directory as needed.
When I need data checking, reports, or any 
database related task:
1. Never execute queries directly
2. Provide raw SQL query only — formatted and clean
3. Add comments explaining what each part does:
   -- This gets all users who ordered this month
4. Warn me if the query might be slow:
   - No index on filtered column
   - Full table scan
   - Large joins
5. Show me the expected output columns so I know 
   what to expect in pgAdmin
6. Wait for me to run it in pgAdmin and paste 
   the results back before proceeding