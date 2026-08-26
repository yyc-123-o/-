# Observed Chapter History Design

## Goal

Populate the diagnosis profile's `prior_chapters` from recorded evidence so later course planning can see earlier chapter performance without claiming a chapter was completed when the system has no explicit completion event.

## Boundary

The input model remains knowledge-point-scoped. A chapter is considered observed only when its primary knowledge point or one of its co-requisite knowledge points has at least one test record. Prerequisite-only records do not create a chapter history entry because they can be reused by several chapters.

## Derivation

For each chapter earlier than `current_chapter_id`:

1. Collect test records for the chapter primary knowledge point and co-requisites.
2. Skip the chapter when no records match.
3. Return accuracy, total test time, covered knowledge points, observed error patterns, and latest evidence timestamp.
4. Select `depth_assigned` from observed accuracy: below 0.60 is `entry`; 0.60 to below 0.80 is `review`; 0.80 or greater is `advanced`.
5. Set `completed_at` to `null`. The timestamp reflects evidence, not completion; the human-readable conclusion states the evidence date and that explicit completion is not yet tracked.

## Error Handling

Invalid current chapter IDs remain rejected by `build_profile()`. Empty learning records return an empty `prior_chapters` list. Timestamps are sorted safely using the typed `TestRecord.timestamp` values.

## Verification

Regression tests will prove that matching chapter evidence produces one history item with correct aggregation, that prerequisite-only evidence does not fabricate history, and that no evidence keeps the list empty.
