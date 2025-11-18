"""
Conflict Analyzer
Uses LLM to analyze validation issues and suggest resolutions
"""

from typing import List, Dict, Any
from langchain_anthropic import ChatAnthropic
from langchain_core.messages import HumanMessage, SystemMessage
import json
import logging

logger = logging.getLogger(__name__)


class ConflictAnalyzer:
    """
    LLM-enhanced conflict analysis and resolution suggestions

    Uses Claude to:
    - Analyze complex validation issues
    - Identify root causes
    - Suggest resolution strategies
    - Prioritize critical issues
    - Generate actionable recommendations
    """

    def __init__(self, llm_model: str = "claude-sonnet-4-20250514"):
        self.llm = ChatAnthropic(model=llm_model, temperature=0.3)

    def analyze(
        self,
        all_issues: List[Dict[str, Any]],
        schedule_context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Analyze all validation issues and provide insights

        Args:
            all_issues: All validation issues from validators
            schedule_context: Context about the schedule being validated

        Returns:
            Analysis report with insights and recommendations
        """
        logger.info(f"Analyzing {len(all_issues)} validation issues with LLM")

        if not all_issues:
            return {
                "summary": "No validation issues found - schedule is compliant",
                "critical_issues": [],
                "recommendations": [],
                "root_causes": []
            }

        # Group issues by severity and category
        grouped_issues = self._group_issues(all_issues)

        # Analyze critical issues
        critical_analysis = self._analyze_critical_issues(
            grouped_issues.get("critical", []),
            schedule_context
        )

        # Identify root causes
        root_causes = self._identify_root_causes(all_issues, schedule_context)

        # Generate recommendations
        recommendations = self._generate_recommendations(
            all_issues, root_causes, schedule_context
        )

        # Create priority matrix
        priority_matrix = self._create_priority_matrix(all_issues)

        return {
            "summary": self._create_summary(all_issues, critical_analysis),
            "critical_issues": grouped_issues.get("critical", []),
            "high_issues": grouped_issues.get("high", []),
            "medium_issues": grouped_issues.get("medium", []),
            "low_issues": grouped_issues.get("low", []),
            "root_causes": root_causes,
            "recommendations": recommendations,
            "priority_matrix": priority_matrix,
            "llm_insights": critical_analysis
        }

    def _group_issues(
        self, issues: List[Dict[str, Any]]
    ) -> Dict[str, List[Dict[str, Any]]]:
        """Group issues by severity"""
        grouped = {
            "critical": [],
            "high": [],
            "medium": [],
            "low": [],
            "info": []
        }

        for issue in issues:
            severity = issue.get("severity", "medium")
            if severity in grouped:
                grouped[severity].append(issue)
            else:
                grouped["medium"].append(issue)

        return grouped

    def _analyze_critical_issues(
        self,
        critical_issues: List[Dict[str, Any]],
        context: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Use LLM to analyze critical issues"""
        if not critical_issues:
            return {"analysis": "No critical issues found"}

        # Prepare prompt
        system_prompt = """You are an expert airline schedule analyst. Analyze the critical validation
issues and provide:
1. Root cause analysis
2. Impact assessment
3. Resolution strategies
4. Priority recommendations

Be concise, actionable, and focus on business impact."""

        issue_summary = self._format_issues_for_llm(critical_issues)

        user_prompt = f"""Analyze these critical schedule validation issues:

Schedule Context:
- Schedule ID: {context.get('schedule_id', 'N/A')}
- Airline: {context.get('airline', 'N/A')}
- Total Flights: {context.get('total_flights', 0)}
- Effective Period: {context.get('effective_from', 'N/A')} to {context.get('effective_to', 'N/A')}

Critical Issues ({len(critical_issues)}):
{issue_summary}

Provide:
1. Root Cause Analysis (what's causing these issues)
2. Business Impact (revenue, operational, regulatory)
3. Resolution Priority (which to fix first and why)
4. Specific Actions (concrete steps to resolve)

Format as JSON with keys: root_causes, business_impact, resolution_priority, recommended_actions"""

        try:
            messages = [
                SystemMessage(content=system_prompt),
                HumanMessage(content=user_prompt)
            ]

            response = self.llm.invoke(messages)

            # Try to parse as JSON
            try:
                analysis = json.loads(response.content)
            except json.JSONDecodeError:
                # If not JSON, return as text
                analysis = {
                    "analysis_text": response.content,
                    "root_causes": ["See analysis_text"],
                    "business_impact": "See analysis_text",
                    "resolution_priority": [],
                    "recommended_actions": []
                }

            return analysis

        except Exception as e:
            logger.error(f"LLM analysis error: {e}")
            return {"error": str(e), "analysis": "LLM analysis failed"}

    def _identify_root_causes(
        self,
        all_issues: List[Dict[str, Any]],
        context: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Identify root causes across all issues"""
        root_causes = []

        # Count issues by type
        issue_types = {}
        for issue in all_issues:
            issue_type = issue.get("issue_type", "unknown")
            if issue_type not in issue_types:
                issue_types[issue_type] = 0
            issue_types[issue_type] += 1

        # Count issues by category
        categories = {}
        for issue in all_issues:
            category = issue.get("category", "unknown")
            if category not in categories:
                categories[category] = 0
            categories[category] += 1

        # Identify patterns
        if issue_types.get("routing_discontinuity", 0) > 5:
            root_causes.append({
                "cause": "Poor aircraft routing",
                "description": "Multiple routing discontinuities suggest suboptimal aircraft routing planning",
                "affected_issues": issue_types["routing_discontinuity"],
                "recommended_fix": "Review and optimize aircraft routing patterns"
            })

        if issue_types.get("insufficient_turnaround", 0) > 3:
            root_causes.append({
                "cause": "Tight scheduling",
                "description": "Multiple turnaround time violations indicate overly aggressive scheduling",
                "affected_issues": issue_types["insufficient_turnaround"],
                "recommended_fix": "Add buffer time between flights or reduce daily utilization"
            })

        if issue_types.get("missing_slot", 0) > 2:
            root_causes.append({
                "cause": "Incomplete slot coordination",
                "description": "Missing airport slots at coordinated airports",
                "affected_issues": issue_types["missing_slot"],
                "recommended_fix": "Request slots from airport coordinators before finalizing schedule"
            })

        if categories.get("crew_validation", 0) > 5:
            root_causes.append({
                "cause": "Crew planning issues",
                "description": "Multiple crew-related violations suggest crew planning needs attention",
                "affected_issues": categories["crew_validation"],
                "recommended_fix": "Review crew assignments and duty time planning"
            })

        return root_causes

    def _generate_recommendations(
        self,
        all_issues: List[Dict[str, Any]],
        root_causes: List[Dict[str, Any]],
        context: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Generate actionable recommendations"""
        recommendations = []

        # Critical recommendations
        critical_count = sum(1 for i in all_issues if i.get("severity") == "critical")

        if critical_count > 0:
            recommendations.append({
                "priority": "immediate",
                "category": "critical_issues",
                "title": f"Resolve {critical_count} Critical Issues",
                "description": "Address all critical issues before schedule publication",
                "actions": [
                    "Review all critical validation failures",
                    "Assign resources to resolve each issue",
                    "Re-validate after corrections",
                    "Do not publish until all critical issues resolved"
                ],
                "timeline": "Before publication"
            })

        # Root cause recommendations
        for root_cause in root_causes:
            recommendations.append({
                "priority": "high",
                "category": "root_cause",
                "title": f"Address: {root_cause['cause']}",
                "description": root_cause["description"],
                "actions": [root_cause["recommended_fix"]],
                "timeline": "Within 1 week"
            })

        # Process improvement recommendations
        if len(all_issues) > 20:
            recommendations.append({
                "priority": "medium",
                "category": "process_improvement",
                "title": "Improve Schedule Planning Process",
                "description": f"{len(all_issues)} total issues suggest schedule planning process needs improvement",
                "actions": [
                    "Implement earlier validation in planning process",
                    "Add validation checkpoints at each planning stage",
                    "Provide planners with real-time validation feedback",
                    "Create schedule planning guidelines document"
                ],
                "timeline": "1-3 months"
            })

        return recommendations

    def _create_priority_matrix(
        self, issues: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Create priority matrix for issue resolution"""
        matrix = {
            "high_impact_high_urgency": [],
            "high_impact_low_urgency": [],
            "low_impact_high_urgency": [],
            "low_impact_low_urgency": []
        }

        for issue in issues:
            severity = issue.get("severity", "medium")
            category = issue.get("category", "")

            # Determine urgency based on severity
            high_urgency = severity in ("critical", "high")

            # Determine impact based on category and description
            high_impact = (
                category in ("slot_validation", "aircraft_validation", "regulatory_validation") or
                "cannot operate" in issue.get("description", "").lower()
            )

            # Place in matrix
            if high_impact and high_urgency:
                matrix["high_impact_high_urgency"].append(issue)
            elif high_impact and not high_urgency:
                matrix["high_impact_low_urgency"].append(issue)
            elif not high_impact and high_urgency:
                matrix["low_impact_high_urgency"].append(issue)
            else:
                matrix["low_impact_low_urgency"].append(issue)

        return matrix

    def _create_summary(
        self,
        all_issues: List[Dict[str, Any]],
        critical_analysis: Dict[str, Any]
    ) -> str:
        """Create executive summary"""
        total = len(all_issues)
        critical = sum(1 for i in all_issues if i.get("severity") == "critical")
        high = sum(1 for i in all_issues if i.get("severity") == "high")
        medium = sum(1 for i in all_issues if i.get("severity") == "medium")
        low = sum(1 for i in all_issues if i.get("severity") == "low")

        summary = f"""Schedule Validation Summary:

Total Issues: {total}
- Critical: {critical} (must fix before publication)
- High: {high} (fix as soon as possible)
- Medium: {medium} (fix before go-live)
- Low: {low} (improvement opportunities)

"""

        if critical > 0:
            summary += f"⚠️  CRITICAL: {critical} blocking issues must be resolved before schedule can be published.\n"

        if high > 0:
            summary += f"⚠️  HIGH: {high} high-priority issues require immediate attention.\n"

        summary += "\nRecommendation: "

        if critical > 0:
            summary += "DO NOT PUBLISH - Resolve all critical issues first."
        elif high > 5:
            summary += "CAUTION - Address high-priority issues before publication."
        elif medium > 10:
            summary += "REVIEW RECOMMENDED - Multiple medium issues should be addressed."
        else:
            summary += "PROCEED WITH CAUTION - Review and address identified issues."

        return summary

    def _format_issues_for_llm(self, issues: List[Dict[str, Any]]) -> str:
        """Format issues for LLM prompt"""
        formatted = []

        for i, issue in enumerate(issues[:15], 1):  # Limit to 15 for token efficiency
            formatted.append(
                f"{i}. {issue.get('issue_type', 'Unknown')}: "
                f"{issue.get('description', 'No description')} "
                f"(Flight: {issue.get('flight_number', 'N/A')})"
            )

        if len(issues) > 15:
            formatted.append(f"... and {len(issues) - 15} more critical issues")

        return "\n".join(formatted)
