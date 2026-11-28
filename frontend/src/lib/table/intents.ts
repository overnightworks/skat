import { throwReaction, type Reaction } from "../../routes/(start)/reaction.ts";

/** What a person may do at the table through a look. */
export interface TableIntents {
    tap(object: Reaction): void;
}

// A refused or failed throw changes nothing, so a tap waits on no answer.
export function tableIntents(id: string): TableIntents {
    return {
        tap(object) {
            void throwReaction(id, object);
        },
    };
}
