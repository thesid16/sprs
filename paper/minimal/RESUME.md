# Resuming this loop

The loop is fully restartable. State lives in two places, both on disk:
- `LOOP_STATE.json` — the cursor (which iteration is next). This is the resume point.
- git history — every iteration is a commit; `git log --oneline` is the audit trail.

`iterate.sh` is atomic: it reverts uncommitted work on entry and advances the cursor
only after committing. So a kill at any moment — session limit, reboot, Ctrl-C —
leaves a clean tree, and the next run redoes exactly the iteration that was interrupted.

    # resume (same command as start)
    setsid nohup bash /home/rohit/sprs-fix/paper_min/run_loop.sh > /dev/null 2>&1 & disown

    # stop after the current iteration
    touch /home/rohit/sprs-fix/paper_min/STOP && rm -f ... # remove STOP to restart

    # watch
    tail -f /home/rohit/sprs-fix/paper_min/loop.log
    cat /home/rohit/sprs-fix/paper_min/LOOP_STATE.json

Each iteration is a COLD READ: the agent is forbidden from reading `iterations/`,
`loop.log` and `LOOP_STATE.json`. It judges main.tex only as it stands. Convergence —
a fresh reader finding nothing necessary to add — is therefore a real signal rather
than the loop agreeing with its own earlier reasoning.
