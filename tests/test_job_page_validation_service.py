from app.services.job_page_validation_service import validate_job_page


def test_validate_job_page_accepts_known_job_board_with_job_text():
    text = """
    Senior Backend Engineer
    About the role
    We are hiring a backend engineer to build APIs for our platform.
    Responsibilities include designing Python services, working with MongoDB,
    and partnering with product managers.
    Qualifications
    5+ years of experience, strong communication skills, and production ownership.
    Benefits include health insurance and remote work.
    Salary range $140,000 - $180,000.
    Apply for this job.
    """

    result = validate_job_page(text, "https://jobs.lever.co/midas/123")

    assert result.is_job_page is True
    assert result.confidence >= 0.55
    assert "known job board domain" in result.signals


def test_validate_job_page_accepts_unknown_domain_with_strong_job_text():
    text = """
    Product Designer
    Job description
    We are looking for a designer to join our team full-time.
    What you will do: lead user research, build prototypes, and collaborate
    with engineers. Requirements include 4+ years of experience with SaaS products.
    Preferred qualifications include strong visual design and systems thinking.
    Compensation is competitive and this role is hybrid in New York.
    Submit application through the form below.
    """

    result = validate_job_page(text, "https://example.com/careers/product-designer")

    assert result.is_job_page is True


def test_validate_job_page_accepts_known_board_with_concise_sales_job():
    text = """
    Founding Sales Development Representative
    Advatix is hiring a sales representative to support outbound pipeline.
    Job type: full-time. Location: remote in the United States.
    You will identify prospects, qualify leads, and partner with account executives.
    Experience with CRM tools, cold outreach, and strong communication is required.
    Submit your application to be considered for this role.
    """

    result = validate_job_page(text, "https://advatixinc.applytojob.com/apply/example")

    assert result.is_job_page is True
    assert "known job board domain" in result.signals


def test_validate_job_page_rejects_blog_article():
    text = """
    How to plan your next product launch
    This article explains how our marketing team thinks about product launches.
    Subscribe to our newsletter for more updates. Share this article with your
    team and leave a comment below. Read more stories from our blog.
    """

    result = validate_job_page(text, "https://example.com/blog/product-launch")

    assert result.is_job_page is False
    assert result.reason == "This page does not look like a job description"


def test_validate_job_page_rejects_shopping_page():
    text = """
    Lightweight laptop stand
    Product details include aluminum construction, adjustable height, and fast
    shipping. Customer reviews mention desk setup improvements. Add to cart or
    continue checkout to complete your order. Related products are available below.
    """

    result = validate_job_page(text, "https://shop.example.com/products/laptop-stand")

    assert result.is_job_page is False


def test_validate_job_page_rejects_very_short_text():
    result = validate_job_page("Software Engineer Apply now", "https://example.com/job")

    assert result.is_job_page is False
    assert "page text is too short" in result.signals
