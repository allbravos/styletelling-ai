# AI.md - StyletellingAI Project Intelligence Document

## PROJECT OVERVIEW
**Project Name**: StyletellingAI (StAI)
**Purpose**: Transform natural language queries into product recommendations using Carol Garcia's styling taxonomy
**Current Phase**: Production/Enhancement
**Last Updated**: 2025-08-28 by Claude
**Session Count**: Initial setup
**Commercial Status**: Experimental product with commercial intent

## CURRENT STATUS SNAPSHOT
**Status**: Active - Working system with enhancement needs
**What's Working**: 
- Core query processing pipeline with LLM attribute extraction
- Streamlit UI with product display and feedback system
- SQLite database with 300+ Amaro products
- Taxonomy matching (7 attributes: Message, Line, Material, Structure, Texture, Surface, Color)
- Occasion/Weather context analysis and exclusion rules
- Category selection and product ranking

**What's Broken**: 
- Limited product catalog (~300 items, too few for diverse recommendations)
- Database not optimized for user feedback storage
- Remote image URLs instead of local storage
- Some categories have insufficient products

**Next Priority**: Tomorrow's presentation preparation
**Blockers**: Need broader product catalog for better recommendations

## TECHNICAL ARCHITECTURE
**Core Components**:
- `run_user_query.py`: Main processing pipeline with streaming interface
- `streamlit_app.py`: Primary UI application 
- `streamlit_orchestrator.py`: UI/backend interface layer
- `streamlit_products.py`: Product display and feedback components
- `cache_runtime.py`: Query caching system for performance
- `streamlit_persistence.py`: Database schema and feedback storage

**Data Flow**:
1. User query → Context analysis (Occasion/Weather)
2. Attribute selection (top 5 from 7 available)
3. Parallel LLM analysis of selected attributes
4. Exclusion rule application based on context
5. Category selection and product matching
6. Ranked product results with UI display

**Key Dependencies**:
- DeepSeek API (via OpenAI client) - cost-efficient LLM choice
- SQLite database (`styletelling.sqlite`)
- Streamlit for UI (deployed on Streamlit Community)
- Concurrent futures for parallel attribute processing

**Critical Files**:
- Database: `styletelling.sqlite` (product catalog + taxonomy)
- Prompts: `./prompts/prompt_*.txt` (8 specialized prompts - see PROMPT SYSTEM section)
- Config: Distributed across files (needs consolidation)

## PROMPT SYSTEM OVERVIEW

**8 Specialized Prompts** working in coordinated pipeline:
1. **Context Analyzer** - Extracts occasion/weather from query
2. **Attribute Selector** - Picks top 5 attributes from 7 available  
3. **6 Attribute Analyzers** - Score specific taxonomy values (Mensagem, Linha, Material, Estrutura, Textura, Superfície)
4. **Category Composer** - Maps attributes to clothing categories

**Key Features**:
- All prompts use 0-10 scoring with JSON output
- 30-word justifications for consistency
- Keyword-based matching with extensive lists
- Brazilian fashion context and seasonal awareness
- Parallel processing of attribute analysis

## IMPLEMENTATION PATTERNS
**Coding Standards**:
- Short, clean functions with single responsibilities
- Streaming interface for real-time UI updates
- Parallel processing for attribute analysis (5 concurrent workers)
- **Prompt Engineering**: 8 specialized prompts with consistent JSON output, 0-10 scoring scales, and 30-word justifications

**Error Handling**:
- Graceful fallbacks for LLM failures
- Cache system with miss tolerance
- Image loading with placeholder fallbacks
- Exception logging without breaking user flow

**Configuration**:
- Attribute mappings in `ATTRIBUTE_INFO` constant
- Exclusion rules in `OCCASION_EXCLUSIONS` and `WEATHER_EXCLUSIONS`
- Prompt file paths in `PROMPT_MAPPING`
- Database path and limits scattered (needs config file)

## CYCLE HISTORY LOG

### Initial Assessment - 2025-08-28 - Analysis
- **Task**: Analyze codebase structure and create AI.md
- **Outcome**: Identified well-structured streaming pipeline with clear separation of concerns
- **Code Changes**: None - analysis only
- **Issues Found**: 
  - Configuration scattered across files
  - Limited product catalog affecting recommendation quality
  - Database schema not optimized for feedback storage
- **Architecture Strengths**: 
  - Clean streaming interface with status updates
  - Parallel attribute processing for performance
  - Smart exclusion rules based on context
  - Deterministic caching system

## LESSONS LEARNED & PATTERNS

### What Works Well
- **Streaming Interface**: Real-time progress updates improve UX significantly
- **Parallel Processing**: 5-worker ThreadPoolExecutor handles attribute analysis efficiently  
- **Context-Aware Exclusions**: Occasion/Weather rules prevent inappropriate recommendations
- **Deterministic Ranking**: Weighted taxonomy scores provide consistent, explainable results
- **Cache System**: Query normalization and envelope storage improve performance
- **Prompt Consistency**: Standardized JSON structures and scoring scales across 8 specialized prompts
- **Attribute-Category Pipeline**: Context → Attribute Selection → Parallel Analysis → Category Scoring
- **Keyword Matching**: Extensive keyword lists in prompts enable precise taxonomy classification  
- **Graduated Scoring**: Universal 0-10 relevance scale with defined confidence ranges
- **Brazilian Fashion Context**: Prompts assume Brazilian market and seasonal patterns

### What Causes Problems
- **Limited Product Data**: ~300 products insufficient for diverse recommendations
- **Configuration Scatter**: Settings spread across multiple files complicates changes
- **Remote Image Dependencies**: External URLs create loading failures and slow performance
- **Database Design**: Current schema not optimized for user feedback analytics
- **Category Imbalance**: Some categories too small for meaningful selection

### Decision History
- **LLM Choice**: Switched from GPT-4o to DeepSeek for cost efficiency (working well)
- **UI Framework**: Migrated Gradio → Streamlit for better customization (feedback system works)
- **Architecture**: Chose streaming over batch processing for better UX
- **Deployment**: Streamlit Community chosen despite open-source requirement risk
- **Database**: SQLite chosen for simplicity, now limiting feedback features

## CONTEXT FOR NEXT SESSION

### Critical Context for Tomorrow's Presentation
**Immediate Priority List** (ranked by importance):
1. Download new Amaro products (winter collection)
2. Add Hering store products 
3. Implement AI recommendation text (independent of available products)
4. Switch back to GPT-4o model (test prompt compatibility)
5. Implement local image storage
6. Audit categories with insufficient products

**Prompt System Notes**:
- All 8 prompts use strict JSON output with standardized 0-10 scoring
- Attribute selection prompt reduces 7 attributes to top 5 for processing efficiency
- Context analyzer handles Brazilian seasonal patterns and event-based weather prediction
- Category composer bridges attribute analysis to specific clothing categories
- Keyword lists in attribute prompts may need updates for new product categories

**Technical Implementation Notes**:
- `ATTRIBUTE_INFO` maps display names to database columns
- Exclusion rules use tuple keys: (formality, time, location, activity)
- Product scoring uses `SUM(CASE WHEN... score * weight)` SQL pattern
- Cache system expects canonical query normalization
- Feedback system requires stable product UIDs across sessions

### Quick Start Context
**If Allan returns after break**: Focus on product catalog expansion - current ~300 items from Amaro insufficient for quality recommendations. Database and processing pipeline solid, need more data.

**If continuing same session**: Ready to tackle product ingestion scripts or configuration consolidation.

**Integration Points**:
- New products need taxonomy classification before matching
- Image URLs should be downloaded and stored locally
- Category balancing may require adjusting selection thresholds
- LLM model switch requires testing prompt compatibility

## SYSTEM HEALTH INDICATORS
- **Performance**: Cache hit rate, query processing time (~2-5 seconds typical)
- **Quality**: Product recommendation relevance, category distribution
- **Reliability**: LLM API success rate, image loading success rate  
- **User Experience**: Feedback submission rate, session completion rate

## DEVELOPMENT WORKFLOW INTEGRATION
**Session Start Protocol**:
1. Check database product count and distribution
2. Verify LLM API connectivity and model version
3. Test sample query end-to-end
4. Review any overnight errors in logs

**Before Major Changes**:
1. Backup `styletelling.sqlite` database
2. Test with cached queries first
3. Verify exclusion rules still apply correctly
4. Check category selection thresholds

**Deployment Checklist**:
1. Verify all prompt files present and readable
2. Test database connection and schema
3. Confirm API keys and model endpoints
4. Test image loading and fallbacks