I'll start by examining the project structure and relevant files to understand the conventions and interfaces I need to work with.

<｜｜DSML｜｜ calls>
<｜｜DSML｜｜ invoke name="bash">
<｜｜DSML｜｜ parameter name="command" string="true">find . -maxdepth 2 -type f -name "*.py" | head -50; echo "---"; ls -la</｜｜DSML｜｜ parameter>
</｜｜DSML｜｜ invoke>
</｜｜DSML｜｜ calls>