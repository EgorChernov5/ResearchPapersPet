from uuid import UUID

from app.research.structures import PreliminaryScoringResult


class BalancedPaperSelector:
    """
    Выбирает уникальные papers с представительством research questions.

    Fallbacks:
        Пустые shortlists пропускаются, а недостающие места заполняются доступными papers.
    """

    def select(
        self,
        scoring_result: PreliminaryScoringResult,
        top_k_expansion: int,
    ) -> list[UUID]:
        """
        Объединяет per-question shortlists в ограниченный глобальный список.

        Parameters:
            scoring_result (PreliminaryScoringResult): Ranked shortlists всех вопросов.
            top_k_expansion (int): Жёсткий глобальный лимит выбранных papers.

        Returns:
            list[UUID]: Уникальные canonical paper IDs в порядке выбора.

        Fallbacks:
            При пересечении shortlists вопрос получает первого ещё не выбранного кандидата.
        """

        if top_k_expansion < 1:
            raise ValueError("Balanced selection limit must be positive")

        # Normalize every ranked shortlist so equal scores always use the canonical ID tie-breaker.
        ranked_shortlists = [
            sorted(
                shortlist.candidates,
                key=lambda candidate: (
                    candidate.preliminary_topic_score is None,
                    -(candidate.preliminary_topic_score or 0.0),
                    str(candidate.paper_id),
                ),
            )
            for shortlist in scoring_result.shortlists
        ]

        # Make one round over questions and choose the first unique candidate for each one.
        selected = []
        selected_ids = set()
        for candidates in ranked_shortlists:
            for candidate in candidates:
                if candidate.paper_id in selected_ids:
                    continue
                selected.append(candidate.paper_id)
                selected_ids.add(candidate.paper_id)
                break
            if len(selected) == top_k_expansion:
                return selected

        # Fill remaining slots by the best score seen for each still-unselected paper.
        remaining_candidates = sorted(
            (candidate for candidates in ranked_shortlists for candidate in candidates),
            key=lambda candidate: (
                candidate.preliminary_topic_score is None,
                -(candidate.preliminary_topic_score or 0.0),
                str(candidate.paper_id),
            ),
        )
        for candidate in remaining_candidates:
            if candidate.paper_id in selected_ids:
                continue
            selected.append(candidate.paper_id)
            selected_ids.add(candidate.paper_id)
            if len(selected) == top_k_expansion:
                break

        return selected
