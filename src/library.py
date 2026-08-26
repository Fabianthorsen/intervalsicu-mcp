from fastmcp import Context, FastMCP

library = FastMCP("library")


@library.tool(tags={"Workouts"}, annotations={"readOnlyHint": True})
async def list_workout_folders(ctx: Context, athlete_id: str = "0") -> list:
    """List all workout folders in the athlete's workout library.

    Args:
        athlete_id: Athlete ID (e.g. 'i12345'). Use '0' for the authenticated user (default).
    """
    r = await ctx.lifespan_context["client"].get(f"/athlete/{athlete_id}/folders")
    return r.json()



@library.tool(tags={"Workouts"})
async def create_workout_folder(
    ctx: Context, folder_name: str, description: str, athlete_id: str = "0"
) -> dict:
    """Create a new workout folder in the athlete's workout library.

    Args:
        folder_name: Name of the folder.
        description: Description of the folder.
        athlete_id: Athlete ID (e.g. 'i12345'). Use '0' for the authenticated user (default).
    """
    body = {"name": folder_name, "description": description}
    r = await ctx.lifespan_context["client"].post(
        f"/athlete/{athlete_id}/folders", json=body
    )
    return {"message": f"Folder '{folder_name}' created.", "status": r.status_code}


@library.tool(tags={"Workouts"})
async def create_workout_in_folder(
    ctx: Context,
    folder_id: int,
    name: str,
    description: str = "",
    type: str | None = None,
    indoor: bool | None = None,
    moving_time: int | None = None,
    target: str | None = None,
    sub_type: str | None = None,
    color: str | None = None,
    tags: list[str] | None = None,
    hide_from_athlete: bool | None = None,
    carbs_per_hour: int | None = None,
    distance: float | None = None,
    file_contents: str | None = None,
    filename: str | None = None,
    athlete_id: str = "0",
) -> dict:
    """Create a workout inside a folder in the athlete's workout library.

    The workout structure can be defined in two ways:
    - Native Intervals.icu format: use the 'description' field with their text interval language.
    - File upload: provide 'file_contents' (raw text) and 'filename' with a .zwo, .mrc, or .erg extension.

    See create_workout for how to write a description: the prose intro plus
    structured interval spec for Ride and Run, prose only for other sports.

    Args:
        folder_id: The ID of the folder to create the workout in.
        name: The workout name.
        description: Workout steps in Intervals.icu native text format, or plain coaching notes.
        type: Sport type (e.g. 'Ride', 'Run', 'Swim').
        indoor: Whether the workout is indoors.
        moving_time: Target duration in seconds.
        target: Primary target metric — AUTO, POWER, HR, or PACE.
        sub_type: Workout sub-type — NONE, COMMUTE, WARMUP, COOLDOWN, or RACE.
        color: Hex color string for the workout (e.g. '#FF5733').
        tags: List of tags to attach to the workout.
        hide_from_athlete: If True, the workout is hidden from the athlete's view.
        carbs_per_hour: Target carbohydrate intake in grams per hour.
        distance: Target distance in metres.
        file_contents: Raw contents of a .zwo, .mrc, or .erg workout file.
        filename: Filename including extension (e.g. 'workout.zwo') when using file_contents.
        athlete_id: Athlete ID (e.g. 'i12345'). Use '0' for the authenticated user (default).
    """
    body: dict = {"name": name, "description": description, "folder_id": folder_id}
    optional = {
        "type": type,
        "indoor": indoor,
        "moving_time": moving_time,
        "target": target,
        "sub_type": sub_type,
        "color": color,
        "tags": tags,
        "hide_from_athlete": hide_from_athlete,
        "carbs_per_hour": carbs_per_hour,
        "distance": distance,
        "file_contents": file_contents,
        "filename": filename,
    }
    body.update({k: v for k, v in optional.items() if v is not None})
    r = await ctx.lifespan_context["client"].post(
        f"/athlete/{athlete_id}/workouts", json=body
    )
    return {"message": f"Workout '{name}' created successfully.", "status": r.status_code}


@library.tool(tags={"Workouts"})
async def update_workout(
    ctx: Context,
    workout_id: int,
    athlete_id: str = "0",
    name: str | None = None,
    description: str | None = None,
    type: str | None = None,
    indoor: bool | None = None,
    moving_time: int | None = None,
    target: str | None = None,
    sub_type: str | None = None,
    color: str | None = None,
    tags: list[str] | None = None,
    hide_from_athlete: bool | None = None,
    carbs_per_hour: int | None = None,
    distance: float | None = None,
) -> dict:
    """Update an existing workout in the athlete's workout library.

    Only the fields you provide will be updated — all others are left unchanged.

    Args:
        workout_id: The workout ID to update. Get IDs from list_workout_folders.
        athlete_id: Athlete ID (e.g. 'i12345'). Use '0' for the authenticated user (default).
        name: New workout name.
        description: Workout steps in Intervals.icu native text format, or plain coaching notes.
        type: Sport type (e.g. 'Ride', 'Run', 'Swim').
        indoor: Whether the workout is indoors.
        moving_time: Target duration in seconds.
        target: Primary target metric — AUTO, POWER, HR, or PACE.
        sub_type: Workout sub-type — NONE, COMMUTE, WARMUP, COOLDOWN, or RACE.
        color: Hex color string for the workout (e.g. '#FF5733').
        tags: List of tags to attach to the workout.
        hide_from_athlete: If True, the workout is hidden from the athlete's view.
        carbs_per_hour: Target carbohydrate intake in grams per hour.
        distance: Target distance in metres.
    """
    body: dict = {}
    optional = {
        "name": name,
        "description": description,
        "type": type,
        "indoor": indoor,
        "moving_time": moving_time,
        "target": target,
        "sub_type": sub_type,
        "color": color,
        "tags": tags,
        "hide_from_athlete": hide_from_athlete,
        "carbs_per_hour": carbs_per_hour,
        "distance": distance,
    }
    body.update({k: v for k, v in optional.items() if v is not None})
    r = await ctx.lifespan_context["client"].put(
        f"/athlete/{athlete_id}/workouts/{workout_id}", json=body
    )
    return {"message": f"Workout {workout_id} updated.", "status": r.status_code}


@library.tool(tags={"Workouts"}, annotations={"destructiveHint": True})
async def delete_workout(
    ctx: Context, workout_id: int, athlete_id: str = "0"
) -> dict:
    """Delete a workout from the athlete's workout library.

    Args:
        workout_id: The workout ID to delete.
        athlete_id: Athlete ID (e.g. 'i12345'). Use '0' for the authenticated user (default).
    """
    r = await ctx.lifespan_context["client"].delete(
        f"/athlete/{athlete_id}/workouts/{workout_id}"
    )
    return {"message": f"Workout {workout_id} deleted.", "status": r.status_code}
