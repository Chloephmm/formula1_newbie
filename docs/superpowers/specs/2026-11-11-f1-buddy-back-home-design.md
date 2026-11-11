# F1 Buddy Back-to-Home Design

## Objective

Add a contextual Back control to the native F1 Buddy popup so a user can leave an active conversation, clear it completely, and return to the welcome screen with the five topic cards.

## Scope

- Add a compact Back arrow to the chat header.
- Show the Back control only when the chat has left its initial welcome state because it contains messages, is waiting for a response, or displays an error.
- Keep the popup open when Back is selected.
- Clear the conversation, draft, pending state, and error state.
- Ignore any response that completes after the user returns home.
- Restore the existing welcome message and five topic cards immediately.

The feature does not modify the chatbot API, response logic, prediction pipeline, data files, or Jolpica integration.

## Interaction Design

The Back button appears at the start of the existing F1 Buddy header, before the F1 brand mark. It uses a simple left arrow so it reads as navigation rather than another window control. Its accessible label is `Back to F1 Buddy home`.

The control is absent on the welcome screen. After a user submits a question, receives a response, or encounters an error, it becomes available. Selecting it performs a destructive reset of only the current chat session; no confirmation is required because the conversation is temporary and the requested behavior is explicitly to start fresh.

Minimize continues to preserve the current state. Close continues to reset the chat and close the panel. Back differs by resetting the chat while leaving the panel open.

## Component and State Changes

### Chat state

Add a reducer action dedicated to returning home. The action returns an open state with empty messages, an empty draft, no pending request, and no error.

### Request lifecycle

The top-level F1 Buddy component increments its existing request version before dispatching the home action. This invalidates any in-flight response so it cannot reappear after the reset.

### Header and panel

`F1BuddyPanel` derives whether the Back control should be visible and passes that state and callback to `ChatHeader`. `ChatHeader` renders the button conditionally while retaining the existing minimize and close controls.

## Visual Treatment

- Reuse the existing dark header, F1 red focus ring, typography, spacing, and button dimensions.
- Use a quiet white arrow with the same hover and keyboard-focus treatment as Minimize and Close.
- Keep the right-side window controls unchanged.
- Avoid adding new labels, badges, colors, or decorative elements.

## Accessibility

- Render a native `button` with `type="button"`.
- Provide the accessible label `Back to F1 Buddy home`.
- Preserve visible keyboard focus using the existing F1 red focus treatment.
- After reset, focus the question input so keyboard users can immediately choose a topic or ask another question.

## Error and Edge-Case Behavior

- Back during a pending response clears the typing indicator and invalidates the response.
- Back after an error clears the error.
- Back after a completed exchange clears all messages.
- The control is not rendered on the welcome screen, preventing a meaningless reset.

## Testing

- Reducer test: the home action returns an open, clean welcome state.
- Reducer test: pending, error, messages, and draft are cleared.
- Header test: Back is rendered with the approved accessible label when enabled.
- Header test: Back is absent on the welcome screen.
- Panel test: Back visibility follows conversation state.
- Integration/source contract test: the top-level component invalidates an in-flight request before returning home.
- Run the complete chatbot test suite, TypeScript validation, scoped linting, and production build.

## Success Criteria

1. A user in any non-welcome chat state can select Back.
2. The popup remains open and immediately shows the original welcome screen.
3. No prior messages, draft text, typing state, or error remains.
4. A late API response cannot repopulate the cleared conversation.
5. Existing Minimize, Close, submission, quick-reply, and data behavior remain unchanged.
